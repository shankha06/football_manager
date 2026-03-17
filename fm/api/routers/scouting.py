"""Scouting assignment endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.db.models import ScoutAssignment, Season, Staff
from fm.world.scouting import ScoutingManager

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────


class ScoutAssignmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scout_id: int
    scout_name: str | None = None
    player_id: int | None = None
    club_id: int
    target_club_id: int | None = None
    region: str | None = None
    started_matchday: int
    duration_weeks: int
    weeks_completed: int
    knowledge_pct: float
    report_ready: bool
    season: int


class CreateAssignment(BaseModel):
    scout_id: int
    # One of these must be provided:
    player_id: int | None = None
    target_club_id: int | None = None
    region: str | None = None
    duration_weeks: int = 4


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/assignments", response_model=list[ScoutAssignmentSchema])
def get_assignments(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get all active scouting assignments for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    assignments = (
        session.query(ScoutAssignment)
        .filter_by(club_id=season.human_club_id, season=season.year)
        .order_by(ScoutAssignment.id.desc())
        .all()
    )

    results = []
    for a in assignments:
        scout_name = None
        if a.scout_id:
            scout = session.get(Staff, a.scout_id)
            if scout:
                scout_name = scout.name

        results.append(
            ScoutAssignmentSchema(
                id=a.id,
                scout_id=a.scout_id,
                scout_name=scout_name,
                player_id=a.player_id,
                club_id=a.club_id,
                target_club_id=a.target_club_id,
                region=a.region,
                started_matchday=a.started_matchday or 0,
                duration_weeks=a.duration_weeks or 4,
                weeks_completed=a.weeks_completed or 0,
                knowledge_pct=a.knowledge_pct or 0.0,
                report_ready=a.report_ready or False,
                season=a.season,
            )
        )

    return results


@router.post("/assignments", response_model=ScoutAssignmentSchema, status_code=201)
def create_assignment(
    body: CreateAssignment,
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Create a new scouting assignment."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    # Validate that exactly one target type is given
    targets = [body.player_id, body.target_club_id, body.region]
    if sum(1 for t in targets if t is not None) != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of: player_id, target_club_id, region.",
        )

    sm = ScoutingManager(session)

    assignment = None
    if body.player_id is not None:
        assignment = sm.assign_scout_to_player(
            club_id=season.human_club_id,
            scout_id=body.scout_id,
            player_id=body.player_id,
            season=season.year,
            matchday=season.current_matchday,
            duration_weeks=body.duration_weeks,
        )
    elif body.region is not None:
        assignment = sm.assign_scout_to_region(
            club_id=season.human_club_id,
            scout_id=body.scout_id,
            region=body.region,
            season=season.year,
            matchday=season.current_matchday,
            duration_weeks=body.duration_weeks,
        )
    elif body.target_club_id is not None:
        assignment = sm.assign_scout_to_club(
            club_id=season.human_club_id,
            scout_id=body.scout_id,
            target_club_id=body.target_club_id,
            season=season.year,
            matchday=season.current_matchday,
            duration_weeks=body.duration_weeks,
        )

    if assignment is None:
        raise HTTPException(
            status_code=409,
            detail="Could not create assignment. Scout may be busy or invalid.",
        )

    session.commit()

    scout_name = None
    scout = session.get(Staff, assignment.scout_id)
    if scout:
        scout_name = scout.name

    return ScoutAssignmentSchema(
        id=assignment.id,
        scout_id=assignment.scout_id,
        scout_name=scout_name,
        player_id=assignment.player_id,
        club_id=assignment.club_id,
        target_club_id=assignment.target_club_id,
        region=assignment.region,
        started_matchday=assignment.started_matchday or 0,
        duration_weeks=assignment.duration_weeks or 4,
        weeks_completed=assignment.weeks_completed or 0,
        knowledge_pct=assignment.knowledge_pct or 0.0,
        report_ready=assignment.report_ready or False,
        season=assignment.season,
    )
