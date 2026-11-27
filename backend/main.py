from time import perf_counter
from contextlib import asynccontextmanager
import asyncio
from fastapi import FastAPI, Request
from app.services.performance import logger
from fastapi.middleware.cors import CORSMiddleware
from app.routes.health import router as health_router
from app.routes.predictions import router as predictions_router
from app.routes.weeks import router as weeks_router
from app.routes.metadata import router as metadata_router
from app.routes.players import router as players_router
from app.routes.espn import router as espn_router
from app.routes.accuracy import router as accuracy_router
from app.services.accuracy_scheduler import AccuracyScheduler
from app.config.security import public_origin, auth_enabled, tailscale_origin
from app.services.auth_middleware import protect_request
from app.routes.account import router as account_router
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AccuracyScheduler()
    scheduler.start()
    app.state.accuracy_scheduler = scheduler
    try:
        yield
    finally:
        await asyncio.to_thread(scheduler.stop)

app = FastAPI(
    title="Fantasy Football AI API",
    version="1.0.0",
    lifespan=lifespan,
)

try:
    allowed_origins = [public_origin()]
    if tailscale_origin():
        allowed_origins.append(tailscale_origin())
except RuntimeError:
    allowed_origins = []
if not auth_enabled():
    allowed_origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"http://(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-League-Connection"],
    expose_headers=["X-Response-Time-ms"],
)

app.middleware("http")(protect_request)


@app.exception_handler(RequestValidationError)
async def safe_account_validation(request: Request, error: RequestValidationError):
    if request.url.path.startswith(("/api/account/", "/api/auth/")):
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in error.errors()
        ]})
    return await request_validation_exception_handler(request, error)


@app.middleware("http")
async def log_request_time(request: Request, call_next):
    started = perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Response-Time-ms"] = (
            f"{(perf_counter() - started) * 1000:.2f}"
        )
        return response
    finally:
        # Exclude query strings, request bodies, and credentials.
        logger.info(
            "request method=%s path=%r status=%s duration_ms=%.2f",
            request.method, request.url.path, status,
            (perf_counter() - started) * 1000,
        )


app.include_router(health_router)
app.include_router(predictions_router)
app.include_router(weeks_router)
app.include_router(metadata_router)
app.include_router(players_router)
app.include_router(espn_router)
app.include_router(accuracy_router)
app.include_router(account_router)
