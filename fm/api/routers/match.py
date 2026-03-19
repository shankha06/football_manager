"""Match simulation and analytics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.api.schemas.match import MatchResult, MatchAnalytics, MatchEventSchema, XGTimelinePoint
from fm.db.models import Fixture, MatchEvent, Season, Club

router = APIRouter()


class NextFixtureInfo(BaseModel):
    fixture_id: int
    matchday: int
    home_club: str
    away_club: str
    home_club_id: int
    away_club_id: int
    is_home: bool


@router.get("/next")
def get_next_fixture(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get info about the human club's next fixture."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    next_md = season.current_matchday + 1
    fixture = (
        session.query(Fixture)
        .filter(
            Fixture.season == season.year,
            Fixture.matchday == next_md,
            Fixture.played.is_(False),
            (Fixture.home_club_id == season.human_club_id)
            | (Fixture.away_club_id == season.human_club_id),
        )
        .first()
    )
    if fixture is None:
        raise HTTPException(status_code=404, detail="No upcoming fixture found.")

    home_club = session.get(Club, fixture.home_club_id)
    away_club = session.get(Club, fixture.away_club_id)

    return {
        "fixture_id": fixture.id,
        "matchday": next_md,
        "home_club": home_club.name if home_club else "Unknown",
        "away_club": away_club.name if away_club else "Unknown",
        "home_club_id": fixture.home_club_id,
        "away_club_id": fixture.away_club_id,
        "is_home": fixture.home_club_id == season.human_club_id,
    }


@router.post("/simulate", response_model=MatchResult)
def simulate_next_match(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Simulate the next matchday and return the human player's match result."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    human_club_id = season.human_club_id
    season_year = season.year

    # Close DI session to avoid DB lock
    session.close()

    from fm.db.database import get_session
    from fm.world.season import SeasonManager

    sm_session = get_session()
    try:
        sm = SeasonManager(sm_session)
        result = sm.advance_matchday(human_club_id=human_club_id)
        sm_session.commit()
    except Exception as e:
        sm_session.rollback()
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}")
    finally:
        sm_session.close()

    # Read results from fresh session
    fresh = get_session()
    try:
        s = fresh.query(Season).order_by(Season.year.desc()).first()
        next_md = result.get("matchday", s.current_matchday if s else 0)
        human_fixture = (
            fresh.query(Fixture)
            .filter(
                Fixture.season == season_year,
                Fixture.matchday == next_md,
                Fixture.played.is_(True),
                (Fixture.home_club_id == human_club_id)
                | (Fixture.away_club_id == human_club_id),
            )
            .first()
        )

        if human_fixture is None:
            raise HTTPException(status_code=404, detail=f"No fixture found for matchday {next_md}.")

        return _fixture_to_result(fresh, human_fixture)
    finally:
        fresh.close()


@router.get("/{fixture_id}/analytics", response_model=MatchAnalytics)
def get_match_analytics(
    fixture_id: int,
    session: Session = Depends(get_db_session),
):
    """Get detailed analytics for a played match."""
    fixture = session.get(Fixture, fixture_id)
    if fixture is None:
        raise HTTPException(status_code=404, detail="Fixture not found.")
    if not fixture.played:
        raise HTTPException(status_code=400, detail="Match has not been played yet.")

    home_club = session.get(Club, fixture.home_club_id)
    away_club = session.get(Club, fixture.away_club_id)

    events = (
        session.query(MatchEvent)
        .filter_by(fixture_id=fixture_id)
        .order_by(MatchEvent.minute)
        .all()
    )

    event_schemas = [
        MatchEventSchema(
            minute=e.minute,
            event_type=e.event_type,
            player_name=e.player.name if e.player else None,
            assist_player_name=e.assist_player.name if e.assist_player else None,
            team_side=e.team_side,
            description=e.description,
        )
        for e in events
    ]

    xg_timeline = _build_xg_timeline(events, fixture)

    return MatchAnalytics(
        fixture_id=fixture.id,
        home_club=home_club.name if home_club else "Unknown",
        away_club=away_club.name if away_club else "Unknown",
        home_club_id=fixture.home_club_id,
        away_club_id=fixture.away_club_id,
        xg_timeline=xg_timeline,
        home_xg=fixture.home_xg,
        away_xg=fixture.away_xg,
        home_possession=fixture.home_possession,
        home_shots=fixture.home_shots,
        away_shots=fixture.away_shots,
        home_shots_on_target=fixture.home_shots_on_target,
        away_shots_on_target=fixture.away_shots_on_target,
        events=event_schemas,
    )


# ── Helpers ───────────────────────────────────────────────────────────────


def _fixture_to_result(session: Session, fixture: Fixture) -> MatchResult:
    """Convert a Fixture ORM object to a MatchResult schema."""
    home_club = session.get(Club, fixture.home_club_id)
    away_club = session.get(Club, fixture.away_club_id)

    events = (
        session.query(MatchEvent)
        .filter_by(fixture_id=fixture.id)
        .order_by(MatchEvent.minute)
        .all()
    )

    event_schemas = [
        MatchEventSchema(
            minute=e.minute,
            event_type=e.event_type,
            player_name=e.player.name if e.player else None,
            assist_player_name=e.assist_player.name if e.assist_player else None,
            team_side=e.team_side,
            description=e.description,
        )
        for e in events
    ]

    motm_name = None
    if fixture.motm_player_id:
        from fm.db.models import Player
        motm = session.get(Player, fixture.motm_player_id)
        if motm:
            motm_name = motm.name

    # Compute pass accuracy
    home_pass_acc = (
        round(fixture.home_passes_completed / fixture.home_passes * 100, 1)
        if fixture.home_passes else None
    )
    away_pass_acc = (
        round(fixture.away_passes_completed / fixture.away_passes * 100, 1)
        if fixture.away_passes else None
    )

    return MatchResult(
        fixture_id=fixture.id,
        home_club=home_club.name if home_club else "Unknown",
        away_club=away_club.name if away_club else "Unknown",
        home_club_id=fixture.home_club_id,
        away_club_id=fixture.away_club_id,
        home_goals=fixture.home_goals or 0,
        away_goals=fixture.away_goals or 0,
        home_xg=fixture.home_xg,
        away_xg=fixture.away_xg,
        home_possession=fixture.home_possession,
        home_shots=fixture.home_shots,
        home_shots_on_target=fixture.home_shots_on_target,
        away_shots=fixture.away_shots,
        away_shots_on_target=fixture.away_shots_on_target,
        attendance=fixture.attendance,
        weather=fixture.weather,
        motm_player_name=motm_name,
        home_passes=fixture.home_passes,
        home_pass_accuracy=home_pass_acc,
        away_passes=fixture.away_passes,
        away_pass_accuracy=away_pass_acc,
        home_tackles=fixture.home_tackles,
        away_tackles=fixture.away_tackles,
        home_interceptions=fixture.home_interceptions,
        away_interceptions=fixture.away_interceptions,
        home_clearances=fixture.home_clearances,
        away_clearances=fixture.away_clearances,
        home_corners=fixture.home_corners,
        away_corners=fixture.away_corners,
        home_fouls=fixture.home_fouls,
        away_fouls=fixture.away_fouls,
        home_offsides=fixture.home_offsides,
        away_offsides=fixture.away_offsides,
        home_yellow_cards=fixture.home_yellow_cards,
        away_yellow_cards=fixture.away_yellow_cards,
        home_red_cards=fixture.home_red_cards,
        away_red_cards=fixture.away_red_cards,
        home_saves=fixture.home_saves,
        away_saves=fixture.away_saves,
        home_crosses=fixture.home_crosses,
        away_crosses=fixture.away_crosses,
        home_dribbles_completed=fixture.home_dribbles_completed,
        away_dribbles_completed=fixture.away_dribbles_completed,
        home_aerials_won=fixture.home_aerials_won,
        away_aerials_won=fixture.away_aerials_won,
        home_big_chances=fixture.home_big_chances,
        away_big_chances=fixture.away_big_chances,
        home_key_passes=fixture.home_key_passes,
        away_key_passes=fixture.away_key_passes,
        events=event_schemas,
    )


def _build_xg_timeline(events: list[MatchEvent], fixture: Fixture) -> list[XGTimelinePoint]:
    """Approximate an xG timeline from shot/goal events."""
    home_xg_cum = 0.0
    away_xg_cum = 0.0
    timeline: list[XGTimelinePoint] = [
        XGTimelinePoint(minute=0, home_cumulative_xg=0.0, away_cumulative_xg=0.0)
    ]

    shot_events = [e for e in events if e.event_type in ("shot", "shot_on_target", "goal")]
    total_home_xg = fixture.home_xg or 0.0
    total_away_xg = fixture.away_xg or 0.0

    home_shot_count = sum(1 for e in shot_events if e.team_side == "home")
    away_shot_count = sum(1 for e in shot_events if e.team_side == "away")

    home_xg_per_shot = total_home_xg / home_shot_count if home_shot_count else 0.0
    away_xg_per_shot = total_away_xg / away_shot_count if away_shot_count else 0.0

    for e in shot_events:
        if e.team_side == "home":
            home_xg_cum += home_xg_per_shot
        else:
            away_xg_cum += away_xg_per_shot

        timeline.append(
            XGTimelinePoint(
                minute=e.minute,
                home_cumulative_xg=round(home_xg_cum, 3),
                away_cumulative_xg=round(away_xg_cum, 3),
            )
        )

    if not timeline or timeline[-1].minute != 90:
        timeline.append(
            XGTimelinePoint(
                minute=90,
                home_cumulative_xg=round(total_home_xg, 3),
                away_cumulative_xg=round(total_away_xg, 3),
            )
        )

    return timeline
