"""Single-owner accounts, revocable sessions, and encrypted ESPN connections."""

from contextlib import contextmanager
from hashlib import sha256
import hmac
import json
import os
import secrets
import sqlite3
from time import time
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock

from app.config.security import account_path, key_path
from app.config.espn_config import ESPNLocalConfig

passwords = PasswordHasher()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(24))
VIEWS = {"team", "optimized", "trade", "matchup", "players", "league", "accuracy"}


class AccountConfigurationError(RuntimeError):
    """Safe, credential-free errors that may be shown to the signed-in owner."""


class AccountStore:
    @contextmanager
    def connect(self):
        path = account_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=10)
        path.chmod(0o600)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS owner (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    password_hash TEXT NOT NULL, theme TEXT NOT NULL DEFAULT 'system', active_connection TEXT);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, csrf TEXT NOT NULL, authenticated INTEGER NOT NULL,
                    expires REAL NOT NULL, last_seen REAL NOT NULL, idle_seconds INTEGER NOT NULL,
                    origin TEXT);
                CREATE TABLE IF NOT EXISTS login_attempts (at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY, league_id INTEGER NOT NULL, season INTEGER NOT NULL,
                    name TEXT NOT NULL, mode TEXT NOT NULL, credentials TEXT,
                    preferred_team_id INTEGER, my_team_id INTEGER, default_view TEXT NOT NULL DEFAULT 'team',
                    status TEXT NOT NULL DEFAULT 'connected', UNIQUE(league_id,season));
            """)
            if "origin" not in {row[1] for row in db.execute("PRAGMA table_info(sessions)")}:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    if "origin" not in {row[1] for row in db.execute("PRAGMA table_info(sessions)")}:
                        db.execute("ALTER TABLE sessions ADD COLUMN origin TEXT")
            if "my_team_id" not in {row[1] for row in db.execute("PRAGMA table_info(connections)")}:
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    if "my_team_id" not in {row[1] for row in db.execute("PRAGMA table_info(connections)")}:
                        db.execute("ALTER TABLE connections ADD COLUMN my_team_id INTEGER")
            with db:
                yield db
        finally:
            db.close()

    def owner(self):
        with self.connect() as db:
            row = db.execute("SELECT username,theme,active_connection FROM owner WHERE id=1").fetchone()
            return dict(row) if row else None

    def set_owner(self, username, password, *, reset=False):
        username = username.strip()
        if not 1 <= len(username) <= 100 or not 8 <= len(password) <= 256:
            raise ValueError("Use a username of 1–100 characters and a password of 8–256 characters.")
        hashed = passwords.hash(password)
        with self.connect() as db:
            if db.execute("SELECT 1 FROM owner").fetchone() and not reset:
                raise ValueError("An owner already exists. Use --reset to replace the login and revoke all sessions.")
            db.execute("INSERT INTO owner(id,username,password_hash) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,password_hash=excluded.password_hash", (username, hashed))
            db.execute("DELETE FROM sessions")
            db.execute("DELETE FROM login_attempts")

    def attempt_login(self, username, password):
        now = time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE at < ?", (now - 900,))
            if db.execute("SELECT COUNT(*) FROM login_attempts").fetchone()[0] >= 20:
                return "limited"
            db.execute("INSERT INTO login_attempts VALUES(?)", (now,))
            owner = db.execute("SELECT username,password_hash FROM owner WHERE id=1").fetchone()
        try:
            valid = passwords.verify(owner["password_hash"] if owner else DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid or owner is None or not hmac.compare_digest(username.encode(), owner["username"].encode()):
            return "invalid"
        with self.connect() as db:
            db.execute("DELETE FROM login_attempts")
        return ("ok", owner["password_hash"])

    def session(self, token, origin=None):
        if not token or len(token) > 256:
            return None
        now = time()
        digest = sha256(token.encode()).hexdigest()
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE token_hash=? AND expires>? AND last_seen+idle_seconds>?", (digest, now, now)).fetchone()
            if row and origin is not None and row["origin"] != origin:
                return None
            if row and now - row["last_seen"] >= 60:
                db.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?", (now, digest))
            return dict(row) if row else None

    def new_session(self, *, authenticated=False, remember=False, previous=None, expected_hash=None, origin=None):
        now = time()
        token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        lifetime = (30 * 86400 if remember else 12 * 3600) if authenticated else 600
        idle = (7 * 86400 if remember else 2 * 3600) if authenticated else 600
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if authenticated and expected_hash is not None:
                owner = db.execute("SELECT password_hash FROM owner WHERE id=1").fetchone()
                if owner is None or not hmac.compare_digest(owner["password_hash"], expected_hash):
                    raise ValueError("The owner login changed during sign-in. Try again.")
            db.execute("DELETE FROM sessions WHERE expires<=? OR last_seen+idle_seconds<=?", (now, now))
            if previous:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (sha256(previous.encode()).hexdigest(),))
            # Bound anonymous setup traffic independently of signed-in sessions.
            db.execute("DELETE FROM sessions WHERE authenticated=0 AND token_hash NOT IN (SELECT token_hash FROM sessions WHERE authenticated=0 ORDER BY last_seen DESC LIMIT 500)")
            db.execute("INSERT INTO sessions(token_hash,csrf,authenticated,expires,last_seen,idle_seconds,origin) VALUES(?,?,?,?,?,?,?)", (sha256(token.encode()).hexdigest(), csrf, int(authenticated), now + lifetime, now, idle, origin))
        return token, csrf, lifetime

    def logout(self, token, all_sessions=False):
        with self.connect() as db:
            if all_sessions:
                db.execute("DELETE FROM sessions")
            elif token:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (sha256(token.encode()).hexdigest(),))

    def vault(self, *, create=False):
        path = key_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock"):
            if not path.exists():
                with self.connect() as db:
                    encrypted_exists = db.execute("SELECT 1 FROM connections WHERE credentials IS NOT NULL LIMIT 1").fetchone()
                if not create or encrypted_exists:
                    raise AccountConfigurationError("The saved-credential encryption key is missing. Restore the key or remove and re-add the affected private leagues.")
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as target:
                    target.write(Fernet.generate_key())
            try:
                return Fernet(path.read_bytes())
            except ValueError as error:
                raise AccountConfigurationError("The saved-credential encryption key is invalid.") from error

    def connections(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT id,league_id,season,name,mode,preferred_team_id,my_team_id,default_view,status FROM connections ORDER BY name,season DESC")]

    def connection(self, id):
        return next((row for row in self.connections() if row["id"] == id), None)

    def private_config(self, id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM connections WHERE id=? AND mode='private'", (id,)).fetchone()
        if row is None:
            raise ValueError("Select a saved private-league connection first.")
        try:
            values = json.loads(self.vault().decrypt(row["credentials"].encode()))
            if values["id"] != id or values["league_id"] != row["league_id"] or values["season"] != row["season"]:
                raise ValueError("Credential binding mismatch")
            return ESPNLocalConfig(league_id=row["league_id"], season=row["season"], swid=values["swid"], espn_s2=values["espn_s2"])
        except (InvalidToken, KeyError, TypeError, ValueError) as error:
            raise AccountConfigurationError("Saved ESPN credentials could not be decrypted. Update the connection or restore its encryption key.") from error

    def save_connection(self, *, league_id, season, name, mode, swid=None, espn_s2=None, id=None):
        existing = next((row for row in self.connections() if row["league_id"] == league_id and row["season"] == season), None)
        id = id or (existing["id"] if existing else uuid4().hex)
        encrypted = None
        if mode == "private":
            encrypted = self.vault(create=True).encrypt(json.dumps({"id": id, "league_id": league_id,
                "season": season, "swid": swid, "espn_s2": espn_s2}).encode()).decode()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM connections").fetchone()[0] >= 10 and not db.execute("SELECT 1 FROM connections WHERE id=?", (id,)).fetchone():
                raise ValueError("Up to 10 saved league connections are supported.")
            db.execute("""INSERT INTO connections(id,league_id,season,name,mode,credentials) VALUES(?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,mode=excluded.mode,credentials=excluded.credentials,status='connected'""",
                (id, league_id, season, name, mode, encrypted))
        return self.connection(id)

    def connection_preferences(self, id, team_id, view):
        if view not in VIEWS:
            raise ValueError("Unknown dashboard view.")
        with self.connect() as db:
            db.execute("UPDATE connections SET preferred_team_id=?,default_view=? WHERE id=?", (team_id, view, id))

    def my_team(self, id, team_id):
        with self.connect() as db:
            db.execute("UPDATE connections SET my_team_id=? WHERE id=?", (team_id, id))

    def preferences(self, *, theme, active_connection):
        if theme not in {"system", "light", "dark"}:
            raise ValueError("Unknown theme.")
        if active_connection and not self.connection(active_connection):
            raise ValueError("The selected saved connection no longer exists.")
        with self.connect() as db:
            db.execute("UPDATE owner SET theme=?,active_connection=? WHERE id=1", (theme, active_connection))

    def mark_expired(self, id):
        with self.connect() as db:
            db.execute("UPDATE connections SET status='reauth_required' WHERE id=?", (id,))

    def delete_connection(self, id):
        row = self.connection(id)
        with self.connect() as db:
            db.execute("DELETE FROM connections WHERE id=?", (id,))
            db.execute("UPDATE owner SET active_connection=NULL WHERE active_connection=?", (id,))
        return row

    def config_for_league(self, league_id, season):
        row = next((row for row in self.connections() if row["league_id"] == league_id and row["season"] == season and row["mode"] == "private"), None)
        return self.private_config(row["id"]) if row else None


accounts = AccountStore()
