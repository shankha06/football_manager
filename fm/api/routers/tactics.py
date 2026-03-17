"""Tactical setup endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.api.schemas.tactics import TacticsRead, TacticsUpdate, TacticalEffectiveness
from fm.db.models import TacticalSetup, Club, Season

router = APIRouter()


@router.get("/", response_model=TacticsRead)
def get_tactics(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get the current tactical setup for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    setup = (
        session.query(TacticalSetup)
        .filter_by(club_id=season.human_club_id)
        .first()
    )
    if setup is None:
        raise HTTPException(status_code=404, detail="Tactical setup not found.")

    return TacticsRead.model_validate(setup)


@router.put("/", response_model=TacticsRead)
def update_tactics(
    body: TacticsUpdate,
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Update the tactical setup for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    setup = (
        session.query(TacticalSetup)
        .filter_by(club_id=season.human_club_id)
        .first()
    )
    if setup is None:
        raise HTTPException(status_code=404, detail="Tactical setup not found.")

    # Apply only the fields that were explicitly provided
    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(setup, field, value)

    session.commit()
    session.refresh(setup)
    return TacticsRead.model_validate(setup)


@router.get("/effectiveness/{opponent_id}", response_model=TacticalEffectiveness)
def get_tactical_effectiveness(
    opponent_id: int,
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Estimate tactical effectiveness against a specific opponent."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    our_setup = (
        session.query(TacticalSetup)
        .filter_by(club_id=season.human_club_id)
        .first()
    )
    opp_setup = (
        session.query(TacticalSetup)
        .filter_by(club_id=opponent_id)
        .first()
    )
    if our_setup is None:
        raise HTTPException(status_code=404, detail="Own tactical setup not found.")
    if opp_setup is None:
        raise HTTPException(status_code=404, detail="Opponent tactical setup not found.")

    # Simple heuristic-based effectiveness score
    score = 50.0
    strengths: list[str] = []
    weaknesses: list[str] = []

    # Pressing advantage vs slow tempo
    if our_setup.pressing in ("high", "very_high") and opp_setup.tempo in ("slow", "very_slow"):
        score += 10
        strengths.append("High press should disrupt their slow build-up")

    # Counter-attack vs high line
    if our_setup.counter_attack and opp_setup.defensive_line == "high":
        score += 12
        strengths.append("Counter-attacks can exploit their high defensive line")

    # Width advantage
    if our_setup.width in ("wide", "very_wide") and opp_setup.width in ("narrow", "very_narrow"):
        score += 8
        strengths.append("Width stretches their narrow shape")

    # Defensive vulnerability against attacking mentality
    if our_setup.mentality in ("attacking", "very_attacking") and opp_setup.mentality in ("attacking", "very_attacking"):
        weaknesses.append("Both teams attacking leaves space at the back")
        score -= 5

    # Possession-based play vs high pressing
    if our_setup.passing_style in ("short", "very_short") and opp_setup.pressing in ("high", "very_high"):
        weaknesses.append("Short passing risks turnovers under their high press")
        score -= 8

    score = max(0.0, min(100.0, score))
    recommendation = None
    if score < 40:
        recommendation = "Consider adjusting tactics -- current setup looks vulnerable."
    elif score > 70:
        recommendation = "Tactics well-suited to this opponent."

    return TacticalEffectiveness(
        score=round(score, 1),
        strengths=strengths,
        weaknesses=weaknesses,
        recommendation=recommendation,
    )
