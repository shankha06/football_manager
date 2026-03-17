"""Pydantic schemas for season progression endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field

from fm.api.schemas.common import StandingBrief
from fm.api.schemas.match import MatchResult


class SeasonState(BaseModel):
    """Current season state overview."""
    season: int = Field(alias="year")
    current_matchday: int
    total_matchdays: int | None = None
    phase: str
    human_club_id: int | None = None
    transfer_window_open: bool = False
    transfer_window_type: str | None = None

    model_config = {"populate_by_name": True}


class AdvanceResult(BaseModel):
    """Result of advancing one matchday."""
    matchday: int
    matches_played: int
    human_result: MatchResult | None = None
    standings: list[StandingBrief] = []
