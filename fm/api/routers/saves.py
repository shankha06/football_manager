"""Save game management endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, reset_game_state
from fm.config import SAVE_DIR, STARTING_SEASON
from fm.db.database import init_db
from fm.db.models import SaveMetadata, Season, Club, League, Player, Manager

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────


class SaveCreate(BaseModel):
    save_name: str
    club_id: int
    manager_name: str = "Player"


class SaveResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    save_name: str
    club_name: str
    manager_name: str | None = None
    season: int
    matchday: int = 0
    created_at: str | None = None
    last_played: str | None = None


class ClubOption(BaseModel):
    id: int
    name: str
    reputation: int
    budget: float
    squad_size: int


class LeagueWithClubs(BaseModel):
    id: int
    name: str
    country: str
    tier: int
    clubs: list[ClubOption]


class IngestResponse(BaseModel):
    leagues: int
    clubs: int
    players: int
    fixtures: int


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/ingest", response_model=IngestResponse)
def run_ingestion(session: Session = Depends(get_db_session)):
    """Run data ingestion if no clubs exist. Returns counts."""
    import logging
    log = logging.getLogger("fm.api.saves")

    try:
        club_count = session.query(Club).count()
    except Exception:
        club_count = 0

    if club_count > 0:
        league_count = session.query(League).count()
        player_count = session.query(Player).count()
        return IngestResponse(leagues=league_count, clubs=club_count,
                              players=player_count, fixtures=0)

    log.info("No clubs found — running data ingestion...")
    try:
        session.close()
        from fm.db.ingestion import ingest_all
        stats = ingest_all()
        return IngestResponse(
            leagues=stats["leagues"], clubs=stats["clubs"],
            players=stats["players"], fixtures=stats["fixtures"],
        )
    except Exception as e:
        log.error(f"Ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Data ingestion failed: {e}")


@router.get("/leagues", response_model=list[LeagueWithClubs])
def list_leagues_with_clubs(session: Session = Depends(get_db_session)):
    """Return all leagues with their clubs for the club selection screen."""
    leagues = session.query(League).order_by(League.tier, League.name).all()
    result = []
    for league in leagues:
        clubs = (
            session.query(Club)
            .filter_by(league_id=league.id)
            .order_by(Club.reputation.desc())
            .all()
        )
        club_options = []
        for club in clubs:
            squad_size = session.query(Player).filter_by(club_id=club.id).count()
            club_options.append(ClubOption(
                id=club.id, name=club.name,
                reputation=club.reputation or 50,
                budget=club.budget or 0.0,
                squad_size=squad_size,
            ))
        result.append(LeagueWithClubs(
            id=league.id, name=league.name,
            country=league.country, tier=league.tier,
            clubs=club_options,
        ))
    return result


@router.post("/", response_model=SaveResponse, status_code=201)
def create_save(
    body: SaveCreate,
    session: Session = Depends(get_db_session),
):
    """Create save with a specific club (data must already be ingested)."""
    club = session.get(Club, body.club_id)
    if club is None:
        raise HTTPException(status_code=404, detail="Club not found.")

    # Mark human club in season
    season_obj = session.query(Season).order_by(Season.year.desc()).first()
    if season_obj:
        season_obj.human_club_id = club.id
        session.commit()

    # Set manager as human
    mgr = session.query(Manager).filter_by(club_id=club.id).first()
    if mgr:
        mgr.is_human = True
        mgr.name = body.manager_name
        session.commit()

    # Create save metadata
    now = datetime.now(timezone.utc).isoformat()
    save = SaveMetadata(
        save_name=body.save_name,
        club_name=club.name,
        manager_name=body.manager_name,
        season=STARTING_SEASON,
        matchday=0,
        db_path=str(SAVE_DIR / "football_manager.db"),
        created_at=now,
        last_played=now,
    )
    session.add(save)
    session.commit()
    session.refresh(save)

    reset_game_state()
    return save


@router.get("/", response_model=list[SaveResponse])
def list_saves(session: Session = Depends(get_db_session)):
    """List all saved games."""
    try:
        return (
            session.query(SaveMetadata)
            .order_by(SaveMetadata.last_played.desc())
            .all()
        )
    except Exception:
        return []


@router.get("/{save_id}", response_model=SaveResponse)
def get_save(save_id: int, session: Session = Depends(get_db_session)):
    save = session.get(SaveMetadata, save_id)
    if save is None:
        raise HTTPException(status_code=404, detail="Save not found.")
    return save


@router.delete("/{save_id}", status_code=204)
def delete_save(save_id: int, session: Session = Depends(get_db_session)):
    save = session.get(SaveMetadata, save_id)
    if save is None:
        raise HTTPException(status_code=404, detail="Save not found.")
    session.delete(save)
    session.commit()
