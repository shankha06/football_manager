"""Pydantic schemas for match simulation and analytics."""
from __future__ import annotations

from pydantic import BaseModel


class MatchEventSchema(BaseModel):
    """A single event in a match (goal, card, sub, etc.)."""
    minute: int
    event_type: str
    player_name: str | None = None
    assist_player_name: str | None = None
    team_side: str | None = None
    description: str | None = None


class MatchResult(BaseModel):
    """Full result of a simulated match."""
    fixture_id: int
    home_club: str
    away_club: str
    home_goals: int
    away_goals: int
    home_xg: float | None = None
    away_xg: float | None = None
    home_possession: float | None = None
    home_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots: int | None = None
    away_shots_on_target: int | None = None
    attendance: int | None = None
    weather: str | None = None
    motm_player_name: str | None = None
    # Passing
    home_passes: int | None = None
    home_pass_accuracy: float | None = None
    away_passes: int | None = None
    away_pass_accuracy: float | None = None
    # Defense
    home_tackles: int | None = None
    away_tackles: int | None = None
    home_interceptions: int | None = None
    away_interceptions: int | None = None
    home_clearances: int | None = None
    away_clearances: int | None = None
    # Set pieces
    home_corners: int | None = None
    away_corners: int | None = None
    home_fouls: int | None = None
    away_fouls: int | None = None
    home_offsides: int | None = None
    away_offsides: int | None = None
    # Discipline
    home_yellow_cards: int | None = None
    away_yellow_cards: int | None = None
    home_red_cards: int | None = None
    away_red_cards: int | None = None
    # GK
    home_saves: int | None = None
    away_saves: int | None = None
    # Advanced
    home_crosses: int | None = None
    away_crosses: int | None = None
    home_dribbles_completed: int | None = None
    away_dribbles_completed: int | None = None
    home_aerials_won: int | None = None
    away_aerials_won: int | None = None
    home_big_chances: int | None = None
    away_big_chances: int | None = None
    home_key_passes: int | None = None
    away_key_passes: int | None = None
    events: list[MatchEventSchema] = []


class XGTimelinePoint(BaseModel):
    """A single point on the xG timeline."""
    minute: int
    home_cumulative_xg: float
    away_cumulative_xg: float


class MatchAnalytics(BaseModel):
    """Detailed analytics for a played match."""
    fixture_id: int
    home_club: str
    away_club: str
    xg_timeline: list[XGTimelinePoint] = []
    home_xg: float | None = None
    away_xg: float | None = None
    home_possession: float | None = None
    home_shots: int | None = None
    away_shots: int | None = None
    home_shots_on_target: int | None = None
    away_shots_on_target: int | None = None
    events: list[MatchEventSchema] = []


class LiveMatchEvent(BaseModel):
    """WebSocket message for live match updates."""
    type: str  # commentary, goal, stats_update, match_end, etc.
    minute: int | None = None
    text: str | None = None
    data: dict | None = None
