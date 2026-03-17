"""Squad and player detail endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.api.schemas.squad import PlayerDetail, PlayerComparison, SquadList, SquadPlayer
from fm.db.models import Player, Season
from fm.db.repositories import PlayerRepository

router = APIRouter()


@router.get("/", response_model=list[SquadPlayer])
def get_squad(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get the full squad list for the human player's club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    players = PlayerRepository.get_squad(session, season.human_club_id)
    if not players:
        return []

    squad_players = [
        SquadPlayer(
            id=p.id,
            name=p.name,
            position=p.position,
            overall=p.overall,
            age=p.age,
            fitness=p.fitness or 100.0,
            morale=p.morale or 65.0,
            form=p.form or 65.0,
            injured_weeks=p.injured_weeks or 0,
            suspended_matches=p.suspended_matches or 0,
            squad_role=p.squad_role or "not_set",
            goals_season=p.goals_season or 0,
            assists_season=p.assists_season or 0,
            wage=p.wage or 0.0,
            market_value=p.market_value or 0.0,
        )
        for p in players
    ]

    return squad_players


@router.get("/{player_id}", response_model=PlayerDetail)
def get_player(
    player_id: int,
    session: Session = Depends(get_db_session),
):
    """Get detailed info for a specific player."""
    player = PlayerRepository.get_by_id(session, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found.")
    return PlayerDetail.model_validate(player)


@router.get("/{player_id}/compare/{other_id}", response_model=PlayerComparison)
def compare_players(
    player_id: int,
    other_id: int,
    session: Session = Depends(get_db_session),
):
    """Compare two players side by side."""
    player_a = PlayerRepository.get_by_id(session, player_id)
    player_b = PlayerRepository.get_by_id(session, other_id)

    if player_a is None:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found.")
    if player_b is None:
        raise HTTPException(status_code=404, detail=f"Player {other_id} not found.")

    return PlayerComparison(
        player_a=PlayerDetail.model_validate(player_a),
        player_b=PlayerDetail.model_validate(player_b),
    )
