"""Authenticate the API independently of the proxy's client IP address."""

import asyncio
import hmac
import sqlite3
from urllib.error import HTTPError, URLError

from requests.exceptions import RequestException

from fastapi.responses import JSONResponse

from app.config.security import auth_enabled, cookie_name, public_origin, request_origin
from app.services.account_store import accounts, AccountConfigurationError
from app.services.performance import logger
from app.services.request_limits import call_limited

PUBLIC_PATHS = {"/api/auth/session", "/api/auth/login", "/api/health/", "/api/health/ready", "/api/public/performance"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def request_io_error(request, error, stage):
    """Report the failing subsystem without logging URLs, cookies, or raw errors."""
    upstream_status = error.code if isinstance(error, HTTPError) else None
    if isinstance(error, RequestException) and error.response is not None:
        upstream_status = error.response.status_code
    logger.error(
        "request_failure stage=%s method=%s path=%r error_type=%s errno=%s upstream_status=%s",
        stage, request.method, request.url.path, type(error).__name__,
        getattr(error, "errno", None), upstream_status,
    )
    if isinstance(error, (URLError, RequestException, TimeoutError, ConnectionError)):
        detail = "Required NFL or ESPN data could not be downloaded."
        if upstream_status is not None:
            detail += f" The upstream source returned HTTP {upstream_status}."
        detail += " Try again later or check the backend logs."
    elif stage == "account":
        detail = "Account storage is unavailable. Check the server account-data volume and permissions."
    elif isinstance(error, FileNotFoundError):
        detail = ("A required backend file is missing. Check the backend logs and confirm "
                  "the trained model checkpoints are present in backend/models/pytorch on the server.")
    elif isinstance(error, PermissionError):
        detail = ("The backend cannot access a required file or directory. "
                  "Check permissions on the model and data mounts.")
    elif isinstance(error, sqlite3.Error):
        detail = "Application storage is unavailable. Check the server data volumes and backend logs."
    else:
        detail = "The backend could not complete a required I/O operation. Check the backend logs."
    return JSONResponse({"detail": detail}, status_code=503)


def security_headers(response):
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Vary"] = "Cookie, Origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


async def protect_request(request, call_next):
    request.state.owner_authenticated = False
    if not auth_enabled():
        return await call_limited(request, call_next)
    path = request.url.path
    try:
        origin = public_origin()
        origin = request_origin(request)
        request.state.login_origin = origin
    except RuntimeError as error:
        return security_headers(JSONResponse({"detail": str(error)}, status_code=503))
    stage = "account"
    try:
        session = await asyncio.to_thread(accounts.session, request.cookies.get(cookie_name(origin)), origin=origin)
        request.state.auth_session = session
        request.state.owner_authenticated = bool(session and session["authenticated"])
        stage = "account" if path.startswith(("/api/account/", "/api/auth/")) else "application"
        protected = path not in PUBLIC_PATHS and request.method != "OPTIONS"
        if protected and not request.state.owner_authenticated:
            response = JSONResponse({"detail": "Sign in to continue."}, status_code=401)
        elif request.method != "OPTIONS" and request.headers.get("origin") not in {None, origin}:
            # This also protects authenticated GET responses from other local
            # applications running on a different port of the same hostname.
            response = JSONResponse({"detail": "This request came from a different application origin."}, status_code=403)
        elif request.method not in SAFE_METHODS:
            # Never trust Forwarded/CF-Connecting-IP/X-Forwarded-For for identity.
            # Exact Origin plus a server-bound token protects login and all writes.
            supplied = request.headers.get("X-CSRF-Token", "")
            if request.headers.get("origin") != origin or not session or not hmac.compare_digest(supplied.encode(), session["csrf"].encode()):
                response = JSONResponse({"detail": "Your session security check expired. Reload the page and try again."}, status_code=403)
            else:
                response = await call_limited(request, call_next)
        else:
            response = await call_limited(request, call_next)
    except AccountConfigurationError as error:
        response = JSONResponse({"detail": str(error)}, status_code=503)
    except (sqlite3.Error, OSError, RequestException) as error:
        response = request_io_error(request, error, stage)
    return security_headers(response)
