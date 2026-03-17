"""Analytics endpoints for xG and form data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.db.models import (
    Club, Fixture, FormHistory, Player, PlayerMatchStats, Season,
)
from fm.db.repositories import FixtureRepository

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────


class XGMatchSummary(BaseModel):
    fixture_id: int
    matchday: int
    opponent: str
    home_away: str  # "home" or "away"
    goals_for: int
    goals_against: int
    xg_for: float | None
    xg_against: float | None


class PlayerFormEntry(BaseModel):
    player_id: int
    player_name: str
    position: str
    form: float
    morale: float
    fitness: float
    last_5_ratings: list[float] = []
    goals_season: int
    assists_season: int


class TeamFormData(BaseModel):
    club_id: int
    club_name: str
    recent_results: list[str]  # "W", "D", "L"
    xg_matches: list[XGMatchSummary]
    player_form: list[PlayerFormEntry]


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/xg", response_model=list[XGMatchSummary])
def get_xg_data(
    last_n: int = Query(default=10, le=38),
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get xG data for the human club's recent matches."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    fixtures = FixtureRepository.get_club_fixtures(
        session, season.human_club_id, season.year
    )
    played = [f for f in fixtures if f.played]
    played = played[-last_n:]  # most recent N

    results = []
    for f in played:
        is_home = f.home_club_id == season.human_club_id
        opponent_id = f.away_club_id if is_home else f.home_club_id
        opponent = session.get(Club, opponent_id)

        results.append(
            XGMatchSummary(
                fixture_id=f.id,
                matchday=f.matchday,
                opponent=opponent.name if opponent else "Unknown",
                home_away="home" if is_home else "away",
                goals_for=(f.home_goals or 0) if is_home else (f.away_goals or 0),
                goals_against=(f.away_goals or 0) if is_home else (f.home_goals or 0),
                xg_for=f.home_xg if is_home else f.away_xg,
                xg_against=f.away_xg if is_home else f.home_xg,
            )
        )

    return results


@router.get("/form", response_model=TeamFormData)
def get_form_data(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get team and player form data for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    club = session.get(Club, season.human_club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found.")

    # Recent results
    fixtures = FixtureRepository.get_club_fixtures(
        session, season.human_club_id, season.year
    )
    played = [f for f in fixtures if f.played]
    recent = played[-5:]

    recent_results = []
    for f in recent:
        is_home = f.home_club_id == season.human_club_id
        gf = (f.home_goals or 0) if is_home else (f.away_goals or 0)
        ga = (f.away_goals or 0) if is_home else (f.home_goals or 0)
        if gf > ga:
            recent_results.append("W")
        elif gf < ga:
            recent_results.append("L")
        else:
            recent_results.append("D")

    # xG for recent matches
    xg_matches = []
    for f in played[-10:]:
        is_home = f.home_club_id == season.human_club_id
        opponent_id = f.away_club_id if is_home else f.home_club_id
        opponent = session.get(Club, opponent_id)
        xg_matches.append(
            XGMatchSummary(
                fixture_id=f.id,
                matchday=f.matchday,
                opponent=opponent.name if opponent else "Unknown",
                home_away="home" if is_home else "away",
                goals_for=(f.home_goals or 0) if is_home else (f.away_goals or 0),
                goals_against=(f.away_goals or 0) if is_home else (f.home_goals or 0),
                xg_for=f.home_xg if is_home else f.away_xg,
                xg_against=f.away_xg if is_home else f.home_xg,
            )
        )

    # Player form
    players = (
        session.query(Player)
        .filter_by(club_id=season.human_club_id)
        .order_by(Player.overall.desc())
        .all()
    )

    player_form_list = []
    for p in players:
        # Get last 5 match ratings from FormHistory
        form_entries = (
            session.query(FormHistory)
            .filter_by(player_id=p.id, season=season.year)
            .order_by(FormHistory.matchday.desc())
            .limit(5)
            .all()
        )
        last_5 = [round(fh.rating, 1) for fh in reversed(form_entries)]

        player_form_list.append(
            PlayerFormEntry(
                player_id=p.id,
                player_name=p.name,
                position=p.position,
                form=p.form or 65.0,
                morale=p.morale or 65.0,
                fitness=p.fitness or 100.0,
                last_5_ratings=last_5,
                goals_season=p.goals_season or 0,
                assists_season=p.assists_season or 0,
            )
        )

    return TeamFormData(
        club_id=season.human_club_id,
        club_name=club.name,
        recent_results=recent_results,
        xg_matches=xg_matches,
        player_form=player_form_list,
    )
