"""FastAPI application factory and entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from fm.api.routers import (
    saves,
    club,
    squad,
    tactics,
    match,
    training,
    transfers,
    season,
    analytics,
    news,
    scouting,
)
from fm.api.websocket import match_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB tables on startup."""
    from fm.db.database import init_db
    init_db()
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    app = FastAPI(
        title="Football Manager v3",
        version="3.0.0",
        description="Backend API for the Football Manager game.",
        lifespan=lifespan,
    )

    # CORS for local dev frontends
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve static assets
    assets_path = Path(__file__).resolve().parent.parent.parent / "assets"
    assets_path.mkdir(exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

    # REST routers
    app.include_router(saves.router, prefix="/api/saves", tags=["saves"])
    app.include_router(club.router, prefix="/api/club", tags=["club"])
    app.include_router(squad.router, prefix="/api/squad", tags=["squad"])
    app.include_router(tactics.router, prefix="/api/tactics", tags=["tactics"])
    app.include_router(match.router, prefix="/api/match", tags=["match"])
    app.include_router(training.router, prefix="/api/training", tags=["training"])
    app.include_router(transfers.router, prefix="/api/transfers", tags=["transfers"])
    app.include_router(season.router, prefix="/api/season", tags=["season"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(news.router, prefix="/api/news", tags=["news"])
    app.include_router(scouting.router, prefix="/api/scouting", tags=["scouting"])

    # WebSocket
    app.include_router(match_ws.router, tags=["websocket"])

    return app


app = create_app()
