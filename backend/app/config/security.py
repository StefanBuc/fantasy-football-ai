"""Fail-closed defaults for the owner-only deployment."""

import os
from ipaddress import ip_address, ip_network
from pathlib import Path
from urllib.parse import urlsplit


def auth_enabled():
    return os.getenv("FANTASY_AUTH_ENABLED", "true").lower() not in {"false", "0", "no"}


def local_development():
    return os.getenv("FANTASY_INSECURE_LOCAL_DEV", "false").lower() in {"true", "1", "yes"}


def public_origin():
    value = os.getenv("FANTASY_PUBLIC_URL", "https://ffa.stefanb.me").strip().rstrip("/")
    url = urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password
            or url.path or url.query or url.fragment):
        raise RuntimeError("Set FANTASY_PUBLIC_URL to the site's HTTPS origin, without a path.")
    if url.scheme != "https" and not (local_development() and url.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise RuntimeError("FANTASY_PUBLIC_URL must use HTTPS outside explicit localhost development.")
    if local_development() and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Insecure development mode is allowed only for a localhost public URL.")
    return value


def account_path():
    return Path(os.getenv("FANTASY_ACCOUNT_PATH", "data/accounts.sqlite3"))


def key_path():
    return Path(os.getenv("FANTASY_ENCRYPTION_KEY_PATH", "data/secrets/credentials.key"))


def tailscale_origin():
    value = os.getenv("FANTASY_TAILSCALE_URL", "").strip().rstrip("/")
    if not value:
        return None
    url = urlsplit(value)
    try:
        address = ip_address(url.hostname or "")
        port = url.port
    except ValueError as error:
        raise RuntimeError("FANTASY_TAILSCALE_URL must use a Tailscale IPv4 address in 100.64.0.0/10.") from error
    if (url.scheme != "http" or address not in ip_network("100.64.0.0/10") or port == 0
            or url.username or url.password or url.path or url.query or url.fragment):
        raise RuntimeError("FANTASY_TAILSCALE_URL must be an HTTP origin on a Tailscale IPv4 address, without a path.")
    return value


def is_loopback_origin(origin):
    if not origin:
        return False
    try:
        url = urlsplit(origin)
        port = url.port
        return (url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
                and port != 0 and not (url.username or url.password or url.path or url.query or url.fragment))
    except ValueError:
        return False


def request_origin(request):
    host = request.headers.get("host", "").lower()
    local = "http://" + host
    if is_loopback_origin(local):
        url = urlsplit(local)
        # Browser Origin headers omit the default HTTP port.
        return f"http://{url.hostname if url.hostname != '::1' else '[::1]'}" + (f":{url.port}" if url.port not in {None, 80} else "")
    private = tailscale_origin()
    # Host is used only to select an explicitly configured entry point. It never
    # authenticates a request; each entry still requires a session and CSRF.
    if private and host == urlsplit(private).netloc.lower():
        return private
    return public_origin()


def cookie_name(origin=None):
    if is_loopback_origin(origin):
        return f"fantasy_session_local_{urlsplit(origin).port or 80}"
    if origin is not None and origin == tailscale_origin():
        return "fantasy_session_tailnet"
    return "fantasy_session_dev" if local_development() else "__Host-fantasy_session"


def cookie_secure(origin):
    return not is_loopback_origin(origin) and not local_development() and origin != tailscale_origin()
