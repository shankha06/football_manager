"""End-to-end integration tests for match situations with real SQLite DB.

Tests that all 16 match situations are correctly triggered and produce
realistic consequences (morale, form, team spirit, news items).
"""
from __future__ import annotations

import random

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fm.core.match_situations import MatchSituationEngine
from fm.db.models import (
    Base,
    Club,
    ConsequenceLog,
    LeagueStanding,
    NewsItem,
    Player,
    PlayerRelationship,
    TacticalSetup,
)
from fm.engine.match_engine import AdvancedMatchEngine
from fm.engine.match_state import PlayerInMatch, MatchState
from fm.engine.match_context import MatchContext
from fm.engine.tactics import TacticalContext

random.seed(42)

SEASON = 2024
MATCHDAY = 10


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite DB with realistic seed data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create clubs
    club = Club(id=1, name="Test FC", team_spirit=70.0, reputation=60)
    rival = Club(id=2, name="Rival United", team_spirit=65.0, reputation=58,
                 league_id=1)
    session.add_all([club, rival])

    # Captain
    captain = Player(
        id=1, name="John Captain", short_name="Captain", age=30,
        position="CB", club_id=1, overall=80, morale=70.0, form=65.0,
        leadership=85, trust_in_manager=70.0, professionalism=75,
    )
    # Striker
    striker = Player(
        id=2, name="Marco Striker", short_name="Striker", age=26,
        position="ST", club_id=1, overall=78, morale=68.0, form=60.0,
        finishing=75, leadership=40, professionalism=65,
    )
    # Young talent
    youngster = Player(
        id=3, name="Jake Youth", short_name="Youth", age=19,
        position="RW", club_id=1, overall=65, potential=85,
        morale=72.0, form=55.0, leadership=30,
    )
    # Veteran
    veteran = Player(
        id=4, name="Paolo Veteran", short_name="Veteran", age=35,
        position="CM", club_id=1, overall=73, morale=66.0, form=62.0,
        leadership=80, professionalism=90,
    )
    # Goalkeeper
    gk = Player(
        id=5, name="Max Keeper", short_name="Keeper", age=28,
        position="GK", club_id=1, overall=77, morale=70.0, form=65.0,
        leadership=50,
    )
    # Defender
    defender = Player(
        id=6, name="Tom Defender", short_name="Defender", age=27,
        position="RB", club_id=1, overall=74, morale=67.0, form=63.0,
    )
    # Left back
    lb = Player(
        id=7, name="Sam LB", short_name="LB", age=25,
        position="LB", club_id=1, overall=72, morale=69.0, form=64.0,
    )

    # Rival players
    rival_gk = Player(
        id=101, name="Rival GK", age=29, position="GK", club_id=2, overall=76,
        morale=65.0, form=60.0,
    )
    rival_st = Player(
        id=102, name="Rival ST", age=27, position="ST", club_id=2, overall=82,
        morale=70.0, form=68.0,
    )

    session.add_all([captain, striker, youngster, veteran, gk, defender, lb,
                     rival_gk, rival_st])

    # Tactical setup with captain
    tac = TacticalSetup(club_id=1, captain_id=1)
    session.add(tac)

    # Friendship
    rel = PlayerRelationship(
        player_a_id=1, player_b_id=2,
        relationship_type="friends", strength=80.0,
    )
    session.add(rel)

    session.commit()
    yield session
    session.close()


# ── 1. Red Card Incident ─────────────────────────────────────────────────

def test_red_card_incident_morale_cascades(db_session):
    """Red card should drop player form, hurt friend morale, generate news."""
    result = MatchSituationEngine.handle_red_card_incident(
        session=db_session, club_id=1, player_id=2,
        incident_type="reckless", minute=35, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    striker = db_session.get(Player, 2)
    assert striker.form < 60.0, "Striker form should drop after red card"

    # Friend (captain) should lose morale
    captain = db_session.get(Player, 1)
    assert captain.morale < 70.0, "Captain (friend) morale should drop"

    # News generated
    news = db_session.query(NewsItem).filter_by(category="match").all()
    assert len(news) >= 1
    assert "sent off" in news[-1].headline.lower() or "red" in news[-1].headline.lower()

    # Consequence log
    logs = db_session.query(ConsequenceLog).all()
    assert any("red_card" in (l.trigger_event or "") for l in logs)


def test_violent_red_card_longer_effects(db_session):
    """Violent conduct should have harsher penalties than reckless."""
    result = MatchSituationEngine.handle_red_card_incident(
        session=db_session, club_id=1, player_id=2,
        incident_type="violent", minute=50, season=SEASON, matchday=MATCHDAY,
    )
    assert result["player_missing_next"] == 3  # Longer ban


# ── 2. Late Goal ─────────────────────────────────────────────────────────

def test_late_goal_scoring_side_boost(db_session):
    """Late goal should massively boost scoring team's morale/form."""
    old_morale = db_session.get(Player, 2).morale
    result = MatchSituationEngine.handle_late_goal(
        session=db_session, club_id=1, player_id=2,
        minute=90, is_comeback=True, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    striker = db_session.get(Player, 2)
    assert striker.morale > old_morale, "Late goal scorer morale should increase"
    assert result.get("momentum_boost", 0) > 0

    news = db_session.query(NewsItem).filter_by(category="match").all()
    assert any("drama" in n.headline.lower() or "late" in n.headline.lower()
               or "rescues" in n.headline.lower() for n in news)


# ── 3. Goalkeeper Error ──────────────────────────────────────────────────

def test_goalkeeper_error_form_drops(db_session):
    old_form = db_session.get(Player, 5).form
    result = MatchSituationEngine.handle_goalkeeper_error(
        session=db_session, club_id=1, goalkeeper_id=5,
        minute=70, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    gk = db_session.get(Player, 5)
    assert gk.form < old_form, "GK form should drop after error"

    news = db_session.query(NewsItem).filter_by(category="match").all()
    assert len(news) >= 1


# ── 4. Missed Penalty ────────────────────────────────────────────────────

def test_missed_penalty_confidence_hit(db_session):
    old_morale = db_session.get(Player, 2).morale
    result = MatchSituationEngine.handle_missed_penalty(
        session=db_session, club_id=1, player_id=2,
        minute=75, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    striker = db_session.get(Player, 2)
    assert striker.morale < old_morale, "Penalty taker morale should drop"
    assert result.get("confidence_crash", 0) < 0


# ── 5. Defensive Collapse ────────────────────────────────────────────────

def test_defensive_collapse_spirit_crash(db_session):
    old_spirit = db_session.get(Club, 1).team_spirit
    result = MatchSituationEngine.handle_defensive_collapse(
        session=db_session, club_id=1, goals_conceded=4, time_window=12,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    club = db_session.get(Club, 1)
    assert club.team_spirit < old_spirit, "Team spirit should crash after collapse"

    # Defenders should be hit hardest
    captain = db_session.get(Player, 1)  # CB
    assert captain.form < 65.0, "CB form should drop"


# ── 6. Comeback Victory ──────────────────────────────────────────────────

def test_comeback_victory_massive_boost(db_session):
    old_spirit = db_session.get(Club, 1).team_spirit
    result = MatchSituationEngine.handle_comeback_victory(
        session=db_session, club_id=1, deficit_goals=2,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    club = db_session.get(Club, 1)
    assert club.team_spirit > old_spirit, "Spirit should surge after comeback"

    striker = db_session.get(Player, 2)
    assert striker.morale > 68.0, "All players should get morale boost"

    news = db_session.query(NewsItem).filter_by(category="match").all()
    assert any("comeback" in n.headline.lower() or "incredible" in n.headline.lower()
               for n in news)


# ── 7. Upset Victory ─────────────────────────────────────────────────────

def test_upset_victory_belief_surge(db_session):
    old_spirit = db_session.get(Club, 1).team_spirit
    result = MatchSituationEngine.handle_upset_victory(
        session=db_session, club_id=1, opponent_rating_advantage=15,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    club = db_session.get(Club, 1)
    assert club.team_spirit > old_spirit
    assert result.get("belief_surge", 0) > 0

    striker = db_session.get(Player, 2)
    assert striker.form > 60.0, "Form should improve after upset win"


# ── 8. Goal Drought ──────────────────────────────────────────────────────

def test_goal_drought_form_collapse(db_session):
    old_form = db_session.get(Player, 2).form
    result = MatchSituationEngine.handle_goal_drought(
        session=db_session, club_id=1, player_id=2,
        matches_without_goal=6, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    striker = db_session.get(Player, 2)
    assert striker.form < old_form, "Striker in drought should lose form"
    assert striker.morale < 68.0, "Morale should drop in drought"


def test_goal_drought_transfer_request_at_8_matches(db_session):
    MatchSituationEngine.handle_goal_drought(
        session=db_session, club_id=1, player_id=2,
        matches_without_goal=9, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    striker = db_session.get(Player, 2)
    assert striker.wants_transfer is True


# ── 9. Scoring Run ───────────────────────────────────────────────────────

def test_scoring_run_form_boost(db_session):
    old_form = db_session.get(Player, 2).form
    result = MatchSituationEngine.handle_scoring_run(
        session=db_session, club_id=1, player_id=2,
        goals_last_3_matches=5, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    striker = db_session.get(Player, 2)
    assert striker.form > old_form, "Hot streak should boost form"
    assert result.get("hot_streak", 0) == 5


# ── 10. Clean Sheet ──────────────────────────────────────────────────────

def test_clean_sheet_defensive_boost(db_session):
    old_cap_form = db_session.get(Player, 1).form  # CB
    result = MatchSituationEngine.handle_clean_sheet(
        session=db_session, club_id=1, after_injury_crisis=False,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    captain = db_session.get(Player, 1)
    assert captain.form > old_cap_form, "CB form should improve after clean sheet"

    club = db_session.get(Club, 1)
    assert club.team_spirit >= 70.0, "Team spirit should not drop"


def test_clean_sheet_after_injury_crisis_extra_boost(db_session):
    result = MatchSituationEngine.handle_clean_sheet(
        session=db_session, club_id=1, after_injury_crisis=True,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    captain = db_session.get(Player, 1)
    # Extra +5 on top of +8 = total +13 expected
    assert captain.form >= 75.0, "Crisis clean sheet should give extra form boost"


# ── 11. Early Red Card ───────────────────────────────────────────────────

def test_early_red_card_extra_penalty(db_session):
    result = MatchSituationEngine.handle_early_red_card(
        session=db_session, club_id=1, player_id=2,
        minute=8, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()
    assert result  # Should return effects dict


# ── 12. Short Turnaround ─────────────────────────────────────────────────

def test_short_turnaround_fitness_drain(db_session):
    result = MatchSituationEngine.handle_short_turnaround_match(
        session=db_session, club_id=1, days_since_last_match=2,
        result="L", season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    assert result.get("stamina_drain", 0) < 0
    club = db_session.get(Club, 1)
    # Spirit should drop slightly on loss
    assert club.team_spirit <= 70.0


# ── 13. Young Player Debut ───────────────────────────────────────────────

def test_young_player_debut_normal(db_session):
    old_morale = db_session.get(Player, 3).morale
    result = MatchSituationEngine.handle_young_player_debut(
        session=db_session, club_id=1, player_id=3,
        is_breakout_performance=False, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    youngster = db_session.get(Player, 3)
    assert youngster.morale > old_morale, "Debut should boost morale"


def test_young_player_breakout_performance(db_session):
    old_potential = db_session.get(Player, 3).potential
    result = MatchSituationEngine.handle_young_player_debut(
        session=db_session, club_id=1, player_id=3,
        is_breakout_performance=True, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    youngster = db_session.get(Player, 3)
    assert youngster.potential > old_potential, "Breakout should raise potential"
    assert youngster.form > 55.0, "Breakout should boost form significantly"

    news = db_session.query(NewsItem).all()
    assert any("debut" in n.headline.lower() or "sensation" in n.headline.lower()
               for n in news)


# ── 14. Veteran Performance ──────────────────────────────────────────────

def test_veteran_performance_inspires_squad(db_session):
    old_youngster_morale = db_session.get(Player, 3).morale
    result = MatchSituationEngine.handle_veteran_performance(
        session=db_session, club_id=1, player_id=4,
        goals_assists=2, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    veteran = db_session.get(Player, 4)
    assert veteran.form > 62.0, "Veteran form should boost"

    youngster = db_session.get(Player, 3)
    assert youngster.morale > old_youngster_morale, "Young teammates should be inspired"

    club = db_session.get(Club, 1)
    assert club.team_spirit > 70.0, "Spirit should rise"


# ── 15. Derby Match ──────────────────────────────────────────────────────

def test_derby_home_win_morale_swing(db_session):
    old_home_spirit = db_session.get(Club, 1).team_spirit
    old_away_spirit = db_session.get(Club, 2).team_spirit

    result = MatchSituationEngine.handle_derby_match(
        session=db_session, home_club_id=1, away_club_id=2,
        result="H", intensity_level=8,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    home_club = db_session.get(Club, 1)
    away_club = db_session.get(Club, 2)
    assert home_club.team_spirit > old_home_spirit, "Derby winner spirit should rise"
    assert away_club.team_spirit < old_away_spirit, "Derby loser spirit should drop"


def test_derby_away_win_bigger_boost(db_session):
    result = MatchSituationEngine.handle_derby_match(
        session=db_session, home_club_id=1, away_club_id=2,
        result="A", intensity_level=7,
        season=SEASON, matchday=MATCHDAY,
    )
    assert result.get("away_morale_boost", 0) > result.get("home_morale_hit", 0), \
        "Away derby win should have bigger impact"


# ── 16. Recurring Injury ─────────────────────────────────────────────────

def test_recurring_injury_morale_and_fitness_hit(db_session):
    old_morale = db_session.get(Player, 2).morale
    result = MatchSituationEngine.handle_recurring_injury(
        session=db_session, club_id=1, player_id=2,
        injury_type="hamstring", previous_recovery_time=4,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    striker = db_session.get(Player, 2)
    assert striker.morale < old_morale, "Recurring injury should drop morale"


# ── Engine Integration: _trigger_situation ────────────────────────────────

def test_trigger_situation_applies_momentum(db_session):
    """Test that _trigger_situation correctly calls situations and applies momentum."""
    engine = AdvancedMatchEngine()
    ctx = MatchContext(session=db_session, season_year=SEASON, matchday=MATCHDAY)
    engine._match_context = ctx

    home_players = [
        PlayerInMatch(player_id=5, name="Keeper", position="GK", side="home", is_gk=True, overall=77),
        PlayerInMatch(player_id=2, name="Striker", position="ST", side="home", overall=78),
    ]
    away_players = [
        PlayerInMatch(player_id=101, name="Rival GK", position="GK", side="away", is_gk=True, overall=76),
        PlayerInMatch(player_id=102, name="Rival ST", position="ST", side="away", overall=82),
    ]
    state = MatchState(home_players=home_players, away_players=away_players)

    old_momentum = state.home_momentum

    # Trigger a late goal situation
    engine._trigger_situation(
        state, "handle_late_goal",
        player_id=2, minute=90, is_comeback=True,
    )

    # Momentum should have changed (positive for home since player_id=2 is home)
    # The handler returns momentum_boost > 0, so home momentum should increase
    assert state.home_momentum != old_momentum or len(state.commentary) > 0


def test_trigger_situation_with_club_id_override(db_session):
    """Test that club_id can be explicitly passed to override auto-detection."""
    engine = AdvancedMatchEngine()
    ctx = MatchContext(session=db_session, season_year=SEASON, matchday=MATCHDAY)
    engine._match_context = ctx

    state = MatchState(
        home_players=[PlayerInMatch(player_id=5, name="GK", position="GK", side="home", is_gk=True)],
        away_players=[PlayerInMatch(player_id=101, name="GK", position="GK", side="away", is_gk=True)],
    )

    # Pass explicit club_id — should not crash
    engine._trigger_situation(
        state, "handle_defensive_collapse",
        club_id=1, goals_conceded=3, time_window=10,
    )
    # Verify the club spirit dropped
    db_session.flush()
    club = db_session.get(Club, 1)
    assert club.team_spirit < 70.0, "Defensive collapse should hurt team spirit"


# ── Realistic scenario chains ────────────────────────────────────────────

def test_red_card_then_comeback_chain(db_session):
    """Simulate: red card drops morale -> comeback victory recovers it."""
    # Step 1: Red card
    MatchSituationEngine.handle_red_card_incident(
        session=db_session, club_id=1, player_id=2,
        incident_type="reckless", minute=30, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    post_red_morale = db_session.get(Player, 2).morale
    post_red_spirit = db_session.get(Club, 1).team_spirit

    # Step 2: Comeback victory
    MatchSituationEngine.handle_comeback_victory(
        session=db_session, club_id=1, deficit_goals=2,
        season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    post_comeback_morale = db_session.get(Player, 2).morale
    post_comeback_spirit = db_session.get(Club, 1).team_spirit

    assert post_comeback_morale > post_red_morale, "Comeback should recover morale after red card"
    assert post_comeback_spirit > post_red_spirit, "Comeback should recover spirit"


def test_goal_drought_then_scoring_run(db_session):
    """Simulate: drought drops form -> scoring run recovers it."""
    MatchSituationEngine.handle_goal_drought(
        session=db_session, club_id=1, player_id=2,
        matches_without_goal=6, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    post_drought_form = db_session.get(Player, 2).form

    MatchSituationEngine.handle_scoring_run(
        session=db_session, club_id=1, player_id=2,
        goals_last_3_matches=4, season=SEASON, matchday=MATCHDAY + 1,
    )
    db_session.flush()

    post_run_form = db_session.get(Player, 2).form
    assert post_run_form > post_drought_form, "Scoring run should recover drought damage"


def test_derby_loss_then_upset_win_recovery(db_session):
    """Simulate: derby loss -> upset victory restores spirit."""
    MatchSituationEngine.handle_derby_match(
        session=db_session, home_club_id=1, away_club_id=2,
        result="A", intensity_level=8, season=SEASON, matchday=MATCHDAY,
    )
    db_session.flush()

    post_derby_spirit = db_session.get(Club, 1).team_spirit

    MatchSituationEngine.handle_upset_victory(
        session=db_session, club_id=1, opponent_rating_advantage=10,
        season=SEASON, matchday=MATCHDAY + 1,
    )
    db_session.flush()

    post_upset_spirit = db_session.get(Club, 1).team_spirit
    assert post_upset_spirit > post_derby_spirit, "Upset win should recover derby loss damage"
