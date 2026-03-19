"""Season progression endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.api.schemas.common import StandingBrief
from fm.api.schemas.match import MatchResult, MatchEventSchema
from fm.api.schemas.season import SeasonState, AdvanceResult
from fm.db.models import (
    Club, Fixture, LeagueStanding, MatchEvent, Season,
)

router = APIRouter()


@router.get("/state", response_model=SeasonState)
def get_season_state(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get the current season state."""
    from fm.world.season import SeasonManager
    sm = SeasonManager(session)
    total_md = sm.get_total_matchdays()
    in_window = sm.is_in_transfer_window()
    window_type = sm.get_transfer_window_type()

    return SeasonState(
        year=season.year,
        current_matchday=season.current_matchday,
        phase=season.phase or "in_season",
        human_club_id=season.human_club_id,
        total_matchdays=total_md,
        transfer_window_open=in_window,
        transfer_window_type=window_type,
    )


@router.get("/standings", response_model=list[StandingBrief])
def get_standings(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get league standings for the human club's league."""
    return _get_league_standings(session, season)


@router.post("/advance", response_model=AdvanceResult)
def advance_matchday_endpoint(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Advance the season by one matchday, simulating all matches."""
    human_club_id = season.human_club_id
    season_year = season.year

    # Close the DI session so SeasonManager can use its own without DB locks
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
        raise HTTPException(status_code=500, detail=f"Failed to advance matchday: {e}")
    finally:
        sm_session.close()

    # Open a fresh session to read results
    fresh = get_session()
    try:
        season = fresh.query(Season).order_by(Season.year.desc()).first()
        matchday = result.get("matchday", season.current_matchday if season else 0)

        human_result = None
        if human_club_id:
            human_fixture = (
                fresh.query(Fixture)
                .filter(
                    Fixture.season == season_year,
                    Fixture.matchday == matchday,
                    Fixture.played.is_(True),
                    (Fixture.home_club_id == human_club_id)
                    | (Fixture.away_club_id == human_club_id),
                )
                .first()
            )
            if human_fixture:
                human_result = _fixture_to_match_result(fresh, human_fixture)

        standings = _get_league_standings(fresh, season) if season else []

        return AdvanceResult(
            matchday=matchday,
            matches_played=result.get("matches", 0),
            human_result=human_result,
            standings=standings,
        )
    finally:
        fresh.close()


# ── Helpers ───────────────────────────────────────────────────────────────


def _fixture_to_match_result(session: Session, fixture: Fixture) -> MatchResult:
    """Convert a Fixture to a MatchResult schema."""
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


def _get_league_standings(session: Session, season: Season) -> list[StandingBrief]:
    """Return league standings for the human club's league."""
    if not season.human_club_id:
        return []

    club = session.get(Club, season.human_club_id)
    if not club or not club.league_id:
        return []

    standings = (
        session.query(LeagueStanding)
        .filter_by(league_id=club.league_id, season=season.year)
        .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
        .all()
    )

    results = []
    for s in standings:
        standing_club = session.get(Club, s.club_id)
        results.append(
            StandingBrief(
                club_id=s.club_id,
                club_name=standing_club.name if standing_club else "Unknown",
                played=s.played or 0,
                won=s.won or 0,
                drawn=s.drawn or 0,
                lost=s.lost or 0,
                goals_for=s.goals_for or 0,
                goals_against=s.goals_against or 0,
                goal_difference=s.goal_difference or 0,
                points=s.points or 0,
                form=s.form or "",
            )
        )

    return results
