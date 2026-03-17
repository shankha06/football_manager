"""Deep consequence chain tests with in-memory SQLite DB.

Tests cascading effects from dropping players, selling players, breaking
promises, overtraining, financial overspend, captain injury, youth
played, and match results.
"""
from __future__ import annotations

import random

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fm.core.consequence_engine import ConsequenceEngine
from fm.core.event_bus import (
    CAPTAIN_INJURED,
    EventBus,
    FINANCIAL_OVERSPEND,
    MATCH_RESULT,
    MATCH_STATS,
    OVERTRAINING,
    PLAYER_DROPPED,
    PLAYER_SOLD,
    PROMISE_BROKEN,
    YOUTH_PLAYED,
)
from fm.db.models import (
    Base,
    BoardExpectation,
    Club,
    ConsequenceLog,
    Player,
    PlayerRelationship,
    Promise,
)

random.seed(42)


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite DB with all tables and seed data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create club
    club = Club(id=1, name="Test FC", team_spirit=70.0)
    session.add(club)

    # Create board expectation
    board = BoardExpectation(
        club_id=1, season=1,
        board_confidence=60.0, fan_happiness=60.0,
        transfer_embargo=False, ultimatum_active=False,
    )
    session.add(board)

    # Player 1: Captain with high leadership
    captain = Player(
        id=1, name="Captain", age=28, position="CB", club_id=1,
        leadership=85, morale=70.0, happiness=70.0, trust_in_manager=70.0,
        consecutive_benched=0, fan_favorite=True, injury_proneness=30,
        potential=80, overall=80, temperament=70,
    )
    # Player 2: Friend of captain
    friend1 = Player(
        id=2, name="Friend One", age=25, position="CM", club_id=1,
        leadership=50, morale=70.0, happiness=65.0, trust_in_manager=65.0,
        consecutive_benched=0, fan_favorite=False, injury_proneness=30,
        potential=75, overall=72, temperament=60,
    )
    # Player 3: Friend of captain
    friend2 = Player(
        id=3, name="Friend Two", age=26, position="ST", club_id=1,
        leadership=45, morale=70.0, happiness=65.0, trust_in_manager=65.0,
        consecutive_benched=0, fan_favorite=False, injury_proneness=30,
        potential=76, overall=73, temperament=55,
    )
    # Player 4: Fan favourite (not captain)
    fan_fav = Player(
        id=4, name="Fan Fav", age=24, position="LW", club_id=1,
        leadership=40, morale=70.0, happiness=65.0, trust_in_manager=65.0,
        consecutive_benched=0, fan_favorite=True, injury_proneness=30,
        potential=82, overall=74, temperament=65,
    )
    # Player 5: Youth player
    youth = Player(
        id=5, name="Youth Star", age=19, position="CAM", club_id=1,
        leadership=30, morale=70.0, happiness=65.0, trust_in_manager=65.0,
        consecutive_benched=0, fan_favorite=False, injury_proneness=30,
        potential=85, overall=62, temperament=50,
    )
    session.add_all([captain, friend1, friend2, fan_fav, youth])

    # Relationships: captain <-> friend1, captain <-> friend2
    rel1 = PlayerRelationship(player_a_id=1, player_b_id=2, relationship_type="friends", strength=75.0)
    rel2 = PlayerRelationship(player_a_id=1, player_b_id=3, relationship_type="close_friends", strength=85.0)
    session.add_all([rel1, rel2])

    session.commit()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDroppingCaptain:
    """Dropping captain 3 times should hurt morale, trust, and friends."""

    def test_dropping_captain_3_times_hurts_morale(self, db_session: Session):
        ce = ConsequenceEngine(db_session)
        captain = db_session.get(Player, 1)
        initial_happiness = captain.happiness
        initial_trust = captain.trust_in_manager

        for md in range(1, 4):
            captain.consecutive_benched = md  # simulate incrementing
            ce._handle_player_dropped(
                PLAYER_DROPPED,
                player_id=1, club_id=1, matchday=md, season=1,
            )

        db_session.flush()
        captain = db_session.get(Player, 1)
        assert captain.happiness < initial_happiness, "Happiness should drop"
        assert captain.trust_in_manager < initial_trust, "Trust should drop"

        # Friends should lose morale
        friend1 = db_session.get(Player, 2)
        assert friend1.morale < 70.0, f"Friend1 morale should drop: {friend1.morale}"


class TestSellingCaptain:
    """Selling captain (fan favourite) should cascade to fans and friends."""

    def test_selling_captain_cascading_effect(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        # Record initial values
        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        initial_fan_happiness = board.fan_happiness
        friend1 = db_session.get(Player, 2)
        initial_friend_morale = friend1.morale

        ce._handle_player_sold(
            PLAYER_SOLD,
            player_id=1, club_id=1, buyer_club_id=99, matchday=5, season=1,
        )
        db_session.flush()

        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        assert board.fan_happiness < initial_fan_happiness, "Fan happiness should drop"

        friend1 = db_session.get(Player, 2)
        assert friend1.morale < initial_friend_morale, "Friend morale should drop"


class TestPromiseBroken:
    """Breaking a promise to unhappy player should trigger transfer request."""

    def test_promise_broken_then_transfer_request(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        # Make player unhappy first
        player = db_session.get(Player, 2)
        player.happiness = 50.0  # will go below 30 after -25

        promise = Promise(
            id=1, player_id=2, club_id=1, promise_type="playing_time",
            made_matchday=1, deadline_matchday=10, season=1,
        )
        db_session.add(promise)
        db_session.flush()

        ce._handle_promise_broken(
            PROMISE_BROKEN,
            promise_id=1, player_id=2, club_id=1, matchday=10, season=1,
        )
        db_session.flush()

        player = db_session.get(Player, 2)
        assert player.wants_transfer is True, "Player should want a transfer"
        promise = db_session.get(Promise, 1)
        assert promise.broken is True, "Promise should be marked broken"


class TestOvertraining:
    """Overtraining should increase injury_proneness by 20."""

    def test_overtraining_then_injury_proneness(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        player = db_session.get(Player, 3)
        initial_ip = player.injury_proneness

        ce._handle_overtraining(
            OVERTRAINING,
            player_id=3, club_id=1, matchday=5, season=1,
        )
        db_session.flush()

        player = db_session.get(Player, 3)
        assert player.injury_proneness == initial_ip + 20, (
            f"Injury proneness should increase by 20: {player.injury_proneness} vs {initial_ip + 20}"
        )


class TestFinancialEscalation:
    """3 matchdays overspend -> transfer_embargo; 6 matchdays -> ultimatum."""

    def test_financial_escalation(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        # 3 consecutive matchdays
        ce._handle_financial_overspend(
            FINANCIAL_OVERSPEND,
            club_id=1, matchday=3, season=1, consecutive_matchdays=3,
        )
        db_session.flush()

        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        assert board.transfer_embargo is True, "Transfer embargo should be active at 3 matchdays"
        assert board.ultimatum_active is False, "Ultimatum should not be active yet"

        # 6 consecutive matchdays
        ce._handle_financial_overspend(
            FINANCIAL_OVERSPEND,
            club_id=1, matchday=6, season=1, consecutive_matchdays=6,
        )
        db_session.flush()

        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        assert board.ultimatum_active is True, "Ultimatum should be active at 6 matchdays"


class TestCaptainInjury:
    """Captain injured should drop team spirit and squad morale."""

    def test_captain_injury_cascades(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        club = db_session.get(Club, 1)
        initial_spirit = club.team_spirit

        ce._handle_captain_injured(
            CAPTAIN_INJURED,
            player_id=1, club_id=1, matchday=5, season=1,
        )
        db_session.flush()

        club = db_session.get(Club, 1)
        assert club.team_spirit < initial_spirit, "Team spirit should drop"

        # Squad mates should lose morale
        friend1 = db_session.get(Player, 2)
        assert friend1.morale < 70.0, f"Squad mate morale should drop: {friend1.morale}"


class TestYouthPlayed:
    """Playing a youth player (age <= 21) should increase potential."""

    def test_youth_played_boosts_potential(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        youth = db_session.get(Player, 5)
        initial_pot = youth.potential

        ce._handle_youth_played(
            YOUTH_PLAYED,
            player_id=5, club_id=1, matchday=5, season=1,
        )
        db_session.flush()

        youth = db_session.get(Player, 5)
        assert youth.potential == initial_pot + 1, (
            f"Youth potential should increase by 1: {youth.potential} vs {initial_pot + 1}"
        )


class TestUnexpectedLoss:
    """Expected win but actual loss should significantly drop board confidence."""

    def test_unexpected_loss_board_confidence(self, db_session: Session):
        random.seed(42)
        ce = ConsequenceEngine(db_session)

        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        initial_conf = board.board_confidence

        ce._handle_match_result(
            MATCH_RESULT,
            club_id=1, home_goals=0, away_goals=2, is_home=True,
            expected_result="win", matchday=5, season=1,
        )
        db_session.flush()

        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        assert board.board_confidence < initial_conf, (
            f"Board confidence should drop: {board.board_confidence} vs {initial_conf}"
        )


class TestExpectedWin:
    """Match result matching expectation should increase board confidence."""

    def test_expected_win_boosts_confidence(self, db_session: Session):
        random.seed(42)
        ce = ConsequenceEngine(db_session)

        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        initial_conf = board.board_confidence

        ce._handle_match_result(
            MATCH_RESULT,
            club_id=1, home_goals=2, away_goals=0, is_home=True,
            expected_result="win", matchday=5, season=1,
        )
        db_session.flush()

        board = db_session.query(BoardExpectation).filter_by(club_id=1).first()
        assert board.board_confidence >= initial_conf, (
            f"Board confidence should not drop: {board.board_confidence} vs {initial_conf}"
        )


class TestConsecutiveDropsCompound:
    """Dropping same player 5 times should be much worse than 3 times."""

    def test_multiple_consecutive_drops_compound(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        # Drop 3 times
        captain_3 = db_session.get(Player, 1)
        for md in range(1, 4):
            captain_3.consecutive_benched = md
            ce._handle_player_dropped(
                PLAYER_DROPPED,
                player_id=1, club_id=1, matchday=md, season=1,
            )
        db_session.flush()
        happiness_after_3 = db_session.get(Player, 1).happiness

        # Reset and drop 5 times
        captain_5 = db_session.get(Player, 1)
        captain_5.happiness = 70.0
        captain_5.trust_in_manager = 70.0
        captain_5.consecutive_benched = 0
        db_session.flush()

        for md in range(1, 6):
            captain_5.consecutive_benched = md
            ce._handle_player_dropped(
                PLAYER_DROPPED,
                player_id=1, club_id=1, matchday=md, season=1,
            )
        db_session.flush()
        happiness_after_5 = db_session.get(Player, 1).happiness

        assert happiness_after_5 < happiness_after_3, (
            f"5 drops ({happiness_after_5}) should be worse than 3 drops ({happiness_after_3})"
        )


class TestEventBusIntegration:
    """Publishing PLAYER_DROPPED via event bus should trigger handler and log."""

    def test_event_bus_fires_handlers(self, db_session: Session):
        bus = EventBus()
        ce = ConsequenceEngine(db_session)
        ce.register_handlers(bus)

        # Ensure player has been benched enough times
        captain = db_session.get(Player, 1)
        captain.consecutive_benched = 3
        db_session.flush()

        bus.publish(
            PLAYER_DROPPED,
            player_id=1, club_id=1, matchday=4, season=1,
        )
        db_session.flush()

        logs = db_session.query(ConsequenceLog).filter_by(trigger_event=PLAYER_DROPPED).all()
        assert len(logs) >= 1, "ConsequenceLog should have at least one entry"


class TestLowPossessionMoraleHit:
    """Team with <40% possession should get a squad morale hit."""

    def test_low_possession_morale_hit(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        # Record initial morale
        captain = db_session.get(Player, 1)
        initial_morale = captain.morale

        ce._handle_poor_performance(
            MATCH_STATS,
            club_id=1, matchday=5, season=1,
            players=[],
            possession_pct=35.0,
            shots_on_target=3,
            won=False,
        )
        db_session.flush()

        captain = db_session.get(Player, 1)
        assert captain.morale < initial_morale, (
            f"Morale should drop with <40% possession: {captain.morale} vs {initial_morale}"
        )


class TestGKHeroicPerformanceConfidence:
    """GK with 5+ saves should get a confidence/morale boost."""

    def test_gk_heroic_performance_confidence(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        # Use player 1 as our test GK
        gk = db_session.get(Player, 1)
        initial_morale = gk.morale

        ce._handle_poor_performance(
            MATCH_STATS,
            club_id=1, matchday=5, season=1,
            players=[
                {
                    "player_id": 1,
                    "rating": 7.5,
                    "fouls": 0,
                    "big_chances_missed": 0,
                    "saves": 7,
                    "is_gk": True,
                    "position": "GK",
                },
            ],
            possession_pct=50.0,
            shots_on_target=5,
            won=True,
        )
        db_session.flush()

        gk = db_session.get(Player, 1)
        assert gk.morale > initial_morale, (
            f"GK morale should increase with 7 saves: {gk.morale} vs {initial_morale}"
        )


class TestMissedBigChancesComposure:
    """Player missing 2+ big chances should get a composure/morale penalty."""

    def test_missed_big_chances_composure(self, db_session: Session):
        ce = ConsequenceEngine(db_session)

        striker = db_session.get(Player, 3)
        initial_morale = striker.morale

        ce._handle_poor_performance(
            MATCH_STATS,
            club_id=1, matchday=5, season=1,
            players=[
                {
                    "player_id": 3,
                    "rating": 6.0,
                    "fouls": 0,
                    "big_chances_missed": 3,
                    "saves": 0,
                    "is_gk": False,
                    "position": "ST",
                },
            ],
            possession_pct=55.0,
            shots_on_target=5,
            won=False,
        )
        db_session.flush()

        striker = db_session.get(Player, 3)
        assert striker.morale < initial_morale, (
            f"Striker morale should drop after missing 3 big chances: {striker.morale} vs {initial_morale}"
        )
