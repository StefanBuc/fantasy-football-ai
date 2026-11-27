"""Authenticate the API independently of the proxy's client IP address."""

import asyncio
import hmac
import sqlite3

from fastapi.responses import JSONResponse

from app.config.security import auth_enabled, cookie_name, public_origin, request_origin
from app.services.account_store import accounts, AccountConfigurationError

PUBLIC_PATHS = {"/api/auth/session", "/api/auth/login", "/api/health/", "/api/health/ready"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


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
        return await call_next(request)
    path = request.url.path
    try:
        origin = public_origin()
        origin = request_origin(request)
        request.state.login_origin = origin
    except RuntimeError as error:
        return security_headers(JSONResponse({"detail": str(error)}, status_code=503))
    try:
        session = await asyncio.to_thread(accounts.session, request.cookies.get(cookie_name(origin)), origin=origin)
        request.state.auth_session = session
        request.state.owner_authenticated = bool(session and session["authenticated"])
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
                response = await call_next(request)
        else:
            response = await call_next(request)
    except AccountConfigurationError as error:
        response = JSONResponse({"detail": str(error)}, status_code=503)
    except (sqlite3.Error, OSError):
        response = JSONResponse({"detail": "Account or application storage is unavailable. Check the server data volumes."}, status_code=503)
    return security_headers(response)
