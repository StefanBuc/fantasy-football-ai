from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr, model_validator
from espn_api.requests.espn_requests import ESPNAccessDenied, ESPNInvalidLeague, ESPNUnknownError

from app.config.security import auth_enabled, cookie_name, cookie_secure, public_origin
from app.services.account_store import accounts
from app.config.espn_config import get_local_espn_config
from app.integrations.espn_fantasy import get_league
from app.services.espn_connection_cache import espn_connection_cache
from app.services.accuracy_jobs import register_league_tracking, accuracy_jobs

router = APIRouter(prefix="/api", tags=["account"])


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: SecretStr = Field(min_length=1, max_length=256)
    remember: bool = False


class ConnectionInput(BaseModel):
    league_id: int = Field(gt=0)
    season: int = Field(ge=2020, le=date.today().year)
    mode: Literal["public", "private"]
    swid: SecretStr | None = Field(default=None, max_length=200)
    espn_s2: SecretStr | None = Field(default=None, max_length=8192)

    @model_validator(mode="after")
    def credentials_required(self):
        if self.mode == "private" and (not self.swid or not self.swid.get_secret_value().strip() or not self.espn_s2 or not self.espn_s2.get_secret_value().strip()):
            raise ValueError("Both SWID and espn_s2 are required for a private league.")
        return self


class Preferences(BaseModel):
    theme: Literal["system", "light", "dark"]
    active_connection: str | None = Field(default=None, max_length=64)


class ConnectionPreferences(BaseModel):
    preferred_team_id: int | None = Field(default=None, gt=0)
    default_view: Literal["team", "optimized", "trade", "matchup", "players", "league", "accuracy"] = "team"


class MyTeamPreference(BaseModel):
    team_id: int | None = Field(default=None, gt=0)


def owner_required(request):
    if not auth_enabled() or not getattr(request.state, "owner_authenticated", False):
        raise HTTPException(401, "Sign in to manage saved connections.")


def set_session(response, token, lifetime, remember, origin):
    response.set_cookie(cookie_name(origin), token, max_age=lifetime if remember else None,
                        secure=cookie_secure(origin), httponly=True, samesite="strict", path="/")


@router.get("/auth/session")
def session_status(request: Request, response: Response):
    if not auth_enabled():
        return {"auth_enabled": False, "authenticated": False}
    origin = public_origin()
    login_origin = request.state.login_origin
    owner = accounts.owner()
    session = getattr(request.state, "auth_session", None)
    if session is None:
        token, csrf, lifetime = accounts.new_session(origin=login_origin)
        set_session(response, token, lifetime, False, login_origin)
    else:
        csrf = session["csrf"]
    authenticated = bool(session and session["authenticated"] and owner)
    return {"auth_enabled": True, "authenticated": authenticated, "configured": owner is not None,
            "csrf_token": csrf, "public_url": origin, "login_origin": login_origin,
            "owner": owner if authenticated else None}


@router.post("/auth/login")
def login(payload: Login, request: Request, response: Response):
    if not auth_enabled():
        raise HTTPException(404)
    if accounts.owner() is None:
        raise HTTPException(503, "Create the owner on the server with: python -m app.scripts.manage_owner")
    result = accounts.attempt_login(payload.username, payload.password.get_secret_value())
    if result == "limited":
        raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.", headers={"Retry-After": "900"})
    if not isinstance(result, tuple) or result[0] != "ok":
        raise HTTPException(401, "Incorrect username or password.")
    try:
        token, csrf, lifetime = accounts.new_session(authenticated=True, remember=payload.remember,
            previous=request.cookies.get(cookie_name(request.state.login_origin)), expected_hash=result[1],
            origin=request.state.login_origin)
    except ValueError as error:
        raise HTTPException(401, "The owner login changed. Sign in again.") from error
    set_session(response, token, lifetime, payload.remember, request.state.login_origin)
    return {"authenticated": True, "csrf_token": csrf, "owner": accounts.owner()}


@router.post("/auth/logout")
def logout(request: Request, response: Response, everywhere: bool = False):
    owner_required(request)
    origin = request.state.login_origin
    accounts.logout(request.cookies.get(cookie_name(origin)), everywhere)
    response.delete_cookie(cookie_name(origin), secure=cookie_secure(origin), httponly=True, samesite="strict", path="/")
    return {"ok": True}


@router.get("/account/connections")
def list_connections(request: Request):
    owner_required(request)
    return {"connections": accounts.connections(), "preferences": accounts.owner()}


def validated_league(league_id, season, swid=None, espn_s2=None):
    try:
        return get_league(league_id=league_id, year=season, swid=swid, espn_s2=espn_s2)
    except ESPNAccessDenied as error:
        raise HTTPException(403, "ESPN did not accept this connection. Update the private-league cookies and try again.") from error
    except ESPNInvalidLeague as error:
        raise HTTPException(404, "ESPN league not found for that season.") from error
    except ESPNUnknownError as error:
        raise HTTPException(502, "ESPN could not validate this connection. Try again shortly.") from error


def save_validated(payload, id=None):
    swid = payload.swid.get_secret_value().strip() if payload.mode == "private" else None
    s2 = payload.espn_s2.get_secret_value().strip() if payload.mode == "private" else None
    league = validated_league(payload.league_id, payload.season, swid, s2)
    try:
        row = accounts.save_connection(league_id=payload.league_id, season=payload.season,
            name=str(league.settings.name), mode=payload.mode, swid=swid, espn_s2=s2, id=id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    register_league_tracking(row["league_id"], row["season"], "saved" if row["mode"] == "private" else "public")
    return row


@router.post("/account/connections")
def add_connection(payload: ConnectionInput, request: Request):
    owner_required(request)
    return save_validated(payload)


@router.put("/account/connections/{id}")
def update_connection(id: str, payload: ConnectionInput, request: Request):
    owner_required(request)
    row = accounts.connection(id)
    if row is None:
        raise HTTPException(404, "Saved connection not found.")
    if (row["league_id"], row["season"]) != (payload.league_id, payload.season):
        raise HTTPException(400, "Add a new connection to change the league ID or season.")
    espn_connection_cache.clear()
    return save_validated(payload, id)


@router.post("/account/import-configured-league")
def import_configured_league(request: Request):
    owner_required(request)
    try:
        config = get_local_espn_config()
    except RuntimeError as error:
        raise HTTPException(400, "No complete server-configured ESPN connection was found.") from error
    return save_validated(ConnectionInput(league_id=config.league_id, season=config.season,
        mode="private", swid=config.swid, espn_s2=config.espn_s2))


@router.post("/account/connections/{id}/connect")
def open_connection(id: str, request: Request):
    owner_required(request)
    row = accounts.connection(id)
    if row is None:
        raise HTTPException(404, "Saved connection not found.")
    league = connection_league(row)
    from app.routes.espn import build_league_connect_response
    register_league_tracking(row["league_id"], row["season"], "saved" if row["mode"] == "private" else "public")
    return build_league_connect_response(league, row["league_id"], row["season"])


def connection_league(row):
    config = accounts.private_config(row["id"]) if row["mode"] == "private" else None
    try:
        league = validated_league(row["league_id"], row["season"], config.swid if config else None,
                                 config.espn_s2 if config else None)
    except HTTPException as error:
        if error.status_code == 403:
            accounts.mark_expired(row["id"])
        raise
    return league


@router.delete("/account/connections/{id}")
def remove_connection(id: str, request: Request):
    owner_required(request)
    row = accounts.delete_connection(id)
    if row:
        with accuracy_jobs.connect() as db:
            accuracy_jobs.prepare(db)
            db.execute("DELETE FROM accuracy_targets WHERE scope=? AND season=?", (f"espn:{row['league_id']}", row["season"]))
    espn_connection_cache.clear()
    return {"ok": True}


@router.patch("/account/preferences")
def update_preferences(payload: Preferences, request: Request):
    owner_required(request)
    try:
        accounts.preferences(theme=payload.theme, active_connection=payload.active_connection)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return accounts.owner()


@router.patch("/account/connections/{id}/preferences")
def update_connection_preferences(id: str, payload: ConnectionPreferences, request: Request):
    owner_required(request)
    if not accounts.connection(id):
        raise HTTPException(404, "Saved connection not found.")
    accounts.connection_preferences(id, payload.preferred_team_id, payload.default_view)
    return accounts.connection(id)


@router.patch("/account/connections/{id}/my-team")
def update_my_team(id: str, payload: MyTeamPreference, request: Request):
    owner_required(request)
    row = accounts.connection(id)
    if row is None:
        raise HTTPException(404, "Saved connection not found.")
    if payload.team_id is not None:
        league = connection_league(row)
        if payload.team_id not in {int(team.team_id) for team in league.teams}:
            raise HTTPException(400, "That team does not belong to this league.")
    accounts.my_team(id, payload.team_id)
    return accounts.connection(id)
