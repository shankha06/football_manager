"""Tests for FastAPI endpoints."""
import pytest


def test_app_creates():
    """The FastAPI app should create without error."""
    from fm.api.app import create_app
    app = create_app()
    assert app.title == "Football Manager v3"


def test_app_has_routes():
    """The app should have all expected route prefixes."""
    from fm.api.app import create_app
    app = create_app()
    paths = [r.path for r in app.routes]
    # Check that key API prefixes are registered
    path_str = " ".join(paths)
    assert "/api/squad" in path_str or any("/api/squad" in p for p in paths)
    assert "/api/season" in path_str or any("/api/season" in p for p in paths)


def test_schemas_import():
    """All Pydantic schemas should import cleanly."""
    from fm.api.schemas.common import PlayerBrief, ClubBrief, PaginatedResponse
    from fm.api.schemas.squad import PlayerDetail, SquadPlayer
    from fm.api.schemas.match import MatchResult as MatchResultSchema
    from fm.api.schemas.tactics import TacticsRead, TacticsUpdate
    from fm.api.schemas.transfers import TransferSearch, TransferBidCreate
    from fm.api.schemas.season import SeasonState as SeasonStateSchema

    # Smoke test: create a PlayerBrief
    pb = PlayerBrief(id=1, name="Test", position="ST", overall=80, age=25)
    assert pb.id == 1


def test_websocket_module_imports():
    """WebSocket match module should import."""
    from fm.api.websocket.match_ws import router
    assert router is not None
