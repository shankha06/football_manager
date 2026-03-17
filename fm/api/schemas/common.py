"""Shared Pydantic models used across multiple routers."""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


# ── Lightweight brief models ──────────────────────────────────────────────


class PlayerBrief(BaseModel):
    """Minimal player representation for lists and summaries."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: str
    overall: int
    age: int
    nationality: str | None = None
    club_id: int | None = None


class ClubBrief(BaseModel):
    """Minimal club representation."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    league_name: str | None = None


class StandingBrief(BaseModel):
    """Single league-table row."""
    model_config = ConfigDict(from_attributes=True)

    club_id: int
    club_name: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    form: str


# ── Pagination ────────────────────────────────────────────────────────────


class PaginatedResponse(BaseModel, Generic[T]):
    """Wrapper for paginated list endpoints."""
    items: list[T]
    total: int
    page: int
    per_page: int
