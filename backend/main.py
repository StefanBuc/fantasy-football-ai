from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.health import router as health_router
from app.routes.predictions import router as predictions_router
from app.routes.weeks import router as weeks_router
from app.routes.metadata import router as metadata_router
from app.routes.players import router as players_router
from app.routes.espn import router as espn_router

app = FastAPI(
    title="Fantasy Football AI API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health_router)
app.include_router(predictions_router)
app.include_router(weeks_router)
app.include_router(metadata_router)
app.include_router(players_router)
app.include_router(espn_router)
