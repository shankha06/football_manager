"""FastAPI dependency injection for database sessions, game state, and managers."""
from __future__ import annotations

from typing import Generator

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from fm.db.database import get_session
from fm.db.models import SaveMetadata, Season
from fm.core.game_state import GameState
from fm.world.season import SeasonManager


# ── Cached singleton for GameState (lives for the server process) ─────────

_game_state: GameState | None = None


def _get_game_state_singleton() -> GameState:
    global _game_state
    if _game_state is None:
        _game_state = GameState()
    return _game_state


def reset_game_state() -> None:
    """Reset the cached game state (call after loading a new save)."""
    global _game_state
    _game_state = None


# ── Dependencies ──────────────────────────────────────────────────────────


def get_db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session that is closed after the request."""
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def get_current_save(
    session: Session = Depends(get_db_session),
) -> SaveMetadata:
    """Return the most recently played save, or raise 404."""
    save = (
        session.query(SaveMetadata)
        .order_by(SaveMetadata.last_played.desc())
        .first()
    )
    if save is None:
        raise HTTPException(status_code=404, detail="No save found. Create a new game first.")
    return save


def get_current_season(
    session: Session = Depends(get_db_session),
) -> Season:
    """Return the active season row, or raise 404."""
    season = session.query(Season).order_by(Season.year.desc()).first()
    if season is None:
        raise HTTPException(status_code=404, detail="No active season found.")
    return season


def get_game_state(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
) -> GameState:
    """Return a loaded GameState, initializing from DB if needed."""
    gs = _get_game_state_singleton()
    if gs.season is None or gs.season.year != season.year:
        gs.load_season(session, season.year)
    return gs


def get_season_manager(
    session: Session = Depends(get_db_session),
) -> SeasonManager:
    """Return a SeasonManager bound to the current session."""
    return SeasonManager(session)
