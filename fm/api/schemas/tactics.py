"""Pydantic schemas for tactical setup endpoints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TacticsRead(BaseModel):
    """Current tactical setup for a club."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    club_id: int
    formation: str = "4-4-2"
    mentality: str = "balanced"
    tempo: str = "normal"
    width: str = "normal"
    pressing: str = "standard"
    passing_style: str = "mixed"
    defensive_line: str = "normal"
    creative_freedom: str = "normal"
    offside_trap: bool = False
    counter_attack: bool = False
    play_out_from_back: bool = False
    time_wasting: str = "off"

    penalty_taker_id: int | None = None
    corner_taker_id: int | None = None
    free_kick_taker_id: int | None = None
    captain_id: int | None = None

    match_plan_winning: str = "hold_lead"
    match_plan_losing: str = "push_forward"
    match_plan_drawing: str = "stay_balanced"


class TacticsUpdate(BaseModel):
    """Partial update for tactical setup. All fields optional."""
    formation: str | None = None
    mentality: str | None = None
    tempo: str | None = None
    width: str | None = None
    pressing: str | None = None
    passing_style: str | None = None
    defensive_line: str | None = None
    creative_freedom: str | None = None
    offside_trap: bool | None = None
    counter_attack: bool | None = None
    play_out_from_back: bool | None = None
    time_wasting: str | None = None

    penalty_taker_id: int | None = None
    corner_taker_id: int | None = None
    free_kick_taker_id: int | None = None
    captain_id: int | None = None

    match_plan_winning: str | None = None
    match_plan_losing: str | None = None
    match_plan_drawing: str | None = None


class TacticalEffectiveness(BaseModel):
    """Estimated effectiveness of current tactics vs an opponent."""
    score: float  # 0-100
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str | None = None
