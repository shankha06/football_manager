"""Training management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.db.models import Club, Season, TrainingSchedule
from fm.world.training import TrainingManager

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────


class TrainingScheduleItem(BaseModel):
    id: int
    focus: str
    intensity: str
    player_id: int | None = None
    player_name: str | None = None
    duration_weeks: int
    weeks_completed: int
    is_match_prep: bool


class TrainingState(BaseModel):
    club_id: int
    focus: str
    intensity: str
    schedules: list[TrainingScheduleItem] = []


class TrainingUpdate(BaseModel):
    focus: str | None = None
    intensity: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/", response_model=TrainingState)
def get_training(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get the current training setup for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    club = session.get(Club, season.human_club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found.")

    tm = TrainingManager(session)
    focus = tm.get_focus(season.human_club_id)
    intensity = tm.get_intensity(season.human_club_id)

    schedules = (
        session.query(TrainingSchedule)
        .filter_by(club_id=season.human_club_id)
        .all()
    )

    schedule_items = []
    for s in schedules:
        player_name = None
        if s.player_id and s.player:
            player_name = s.player.name
        schedule_items.append(
            TrainingScheduleItem(
                id=s.id,
                focus=s.focus,
                intensity=s.intensity or "normal",
                player_id=s.player_id,
                player_name=player_name,
                duration_weeks=s.duration_weeks or 1,
                weeks_completed=s.weeks_completed or 0,
                is_match_prep=s.is_match_prep or False,
            )
        )

    return TrainingState(
        club_id=season.human_club_id,
        focus=focus,
        intensity=str(intensity.value) if hasattr(intensity, "value") else str(intensity),
        schedules=schedule_items,
    )


@router.put("/", response_model=TrainingState)
def update_training(
    body: TrainingUpdate,
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Update the training focus and/or intensity for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    tm = TrainingManager(session)

    if body.focus is not None:
        tm.set_focus(season.human_club_id, body.focus)

    if body.intensity is not None:
        from fm.world.training import TrainingIntensity
        try:
            ti = TrainingIntensity(body.intensity)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid intensity: {body.intensity}. "
                       f"Valid values: {[e.value for e in TrainingIntensity]}",
            )
        tm.set_intensity(season.human_club_id, ti)

    session.commit()

    # Return updated state
    return get_training(session=session, season=season)
