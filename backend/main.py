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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Response-Time-ms"],
)


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
