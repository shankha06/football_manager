"""Club information endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.db.models import Club, Season, BoardExpectation, League

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────


class ClubInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str | None = None
    league_name: str | None = None
    reputation: int
    budget: float
    wage_budget: float
    total_wages: float
    facilities_level: int
    stadium_capacity: int
    stadium_name: str | None = None
    primary_color: str
    secondary_color: str
    training_focus: str
    youth_academy_level: int
    training_facility_level: int
    scouting_network_level: int
    medical_facility_level: int
    board_type: str
    team_spirit: float


class BoardInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    club_id: int
    season: int
    min_league_position: int
    max_league_position: int
    board_confidence: float
    fan_happiness: float
    patience: int
    style_expectation: str
    warnings_issued: int
    ultimatum_active: bool
    transfer_embargo: bool


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/", response_model=ClubInfo)
def get_club(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get the human player's current club info."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set for this season.")

    club = session.get(Club, season.human_club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found.")

    league_name = None
    if club.league_id:
        league = session.get(League, club.league_id)
        if league:
            league_name = league.name

    return ClubInfo(
        id=club.id,
        name=club.name,
        short_name=club.short_name,
        league_name=league_name,
        reputation=club.reputation or 50,
        budget=club.budget or 0.0,
        wage_budget=club.wage_budget or 0.0,
        total_wages=club.total_wages or 0.0,
        facilities_level=club.facilities_level or 5,
        stadium_capacity=club.stadium_capacity or 30000,
        stadium_name=club.stadium_name,
        primary_color=club.primary_color or "#FFFFFF",
        secondary_color=club.secondary_color or "#000000",
        training_focus=club.training_focus or "match_prep",
        youth_academy_level=club.youth_academy_level or 5,
        training_facility_level=club.training_facility_level or 5,
        scouting_network_level=club.scouting_network_level or 3,
        medical_facility_level=club.medical_facility_level or 5,
        board_type=club.board_type or "balanced",
        team_spirit=club.team_spirit or 60.0,
    )


@router.get("/board", response_model=BoardInfo)
def get_board(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get board expectations and confidence for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set for this season.")

    board = (
        session.query(BoardExpectation)
        .filter_by(club_id=season.human_club_id)
        .first()
    )
    if board is None:
        raise HTTPException(status_code=404, detail="Board expectations not found.")

    return board
