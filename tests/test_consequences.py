"""Tests for the consequence system."""
import pytest


@pytest.fixture
def setup_db():
    """Create an in-memory DB with test data."""
    from fm.db.models import Base, Club, Player, BoardExpectation, PlayerRelationship
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create test club
    club = Club(id=1, name="Test FC", reputation=70, team_spirit=60.0)
    session.add(club)

    # Create board expectation
    board = BoardExpectation(
        club_id=1, season=2024, board_confidence=60.0,
        fan_happiness=60.0, min_league_position=5, max_league_position=10,
    )
    session.add(board)

    # Create players
    captain = Player(
        id=1, name="Captain", age=28, position="CM", club_id=1,
        leadership=85, happiness=70.0, morale=70.0,
        trust_in_manager=65.0, fan_favorite=True,
    )
    friend1 = Player(
        id=2, name="Friend", age=25, position="ST", club_id=1,
        happiness=65.0, morale=65.0, trust_in_manager=60.0,
    )
    friend2 = Player(
        id=3, name="Friend2", age=23, position="LW", club_id=1,
        happiness=60.0, morale=60.0, trust_in_manager=55.0,
    )

    session.add_all([captain, friend1, friend2])

    # Relationships
    rel = PlayerRelationship(
        player_a_id=1, player_b_id=2,
        relationship_type="friends", strength=70.0,
    )
    session.add(rel)

    session.commit()
    yield session
    session.close()


def test_selling_fan_favorite_drops_happiness(setup_db):
    """Selling a fan favorite should reduce fan happiness."""
    from fm.core.consequence_engine import ConsequenceEngine
    from fm.db.models import BoardExpectation

    session = setup_db
    engine = ConsequenceEngine(session)

    board_before = session.query(BoardExpectation).filter_by(club_id=1).first()
    fan_before = board_before.fan_happiness

    engine._handle_player_sold(
        "player_sold", player_id=1, club_id=1, buyer_club_id=99,
        matchday=5, season=2024,
    )
    session.flush()

    board_after = session.query(BoardExpectation).filter_by(club_id=1).first()
    assert board_after.fan_happiness < fan_before, \
        f"Fan happiness should drop: {board_after.fan_happiness} < {fan_before}"


def test_broken_promise_triggers_wants_transfer(setup_db):
    """Breaking a promise should reduce happiness and potentially trigger transfer request."""
    from fm.core.consequence_engine import ConsequenceEngine
    from fm.db.models import Player, Promise

    session = setup_db

    # Create a promise
    promise = Promise(
        id=1, player_id=2, club_id=1, promise_type="playing_time",
        made_matchday=1, deadline_matchday=10, season=2024,
    )
    session.add(promise)
    session.commit()

    # Set player happiness low so -25 triggers wants_transfer
    player = session.get(Player, 2)
    player.happiness = 40.0
    session.commit()

    engine = ConsequenceEngine(session)
    engine._handle_promise_broken(
        "promise_broken", promise_id=1, player_id=2, club_id=1,
        matchday=10, season=2024,
    )
    session.flush()

    player = session.get(Player, 2)
    assert player.happiness <= 15.0  # Was 40, now 40-25=15
    assert player.wants_transfer is True


def test_captain_injury_drops_spirit(setup_db):
    """Captain injury should reduce team spirit."""
    from fm.core.consequence_engine import ConsequenceEngine
    from fm.db.models import Club

    session = setup_db
    club_before = session.get(Club, 1)
    spirit_before = club_before.team_spirit

    engine = ConsequenceEngine(session)
    engine._handle_captain_injured(
        "captain_injured", player_id=1, club_id=1, matchday=5, season=2024,
    )
    session.flush()

    club_after = session.get(Club, 1)
    assert club_after.team_spirit < spirit_before, \
        f"Team spirit should drop: {club_after.team_spirit} < {spirit_before}"


def test_overtraining_increases_injury_risk(setup_db):
    """Overtraining should increase injury proneness."""
    from fm.core.consequence_engine import ConsequenceEngine
    from fm.db.models import Player

    session = setup_db
    player = session.get(Player, 2)
    proneness_before = player.injury_proneness

    engine = ConsequenceEngine(session)
    engine._handle_overtraining(
        "overtraining", player_id=2, club_id=1, matchday=5, season=2024,
    )
    session.flush()

    player = session.get(Player, 2)
    assert player.injury_proneness > proneness_before


def test_financial_overspend_triggers_embargo(setup_db):
    """6+ matchdays of overspending should trigger transfer embargo."""
    from fm.core.consequence_engine import ConsequenceEngine
    from fm.db.models import BoardExpectation

    session = setup_db
    engine = ConsequenceEngine(session)

    engine._handle_financial_overspend(
        "financial_overspend", club_id=1, matchday=10, season=2024, consecutive_matchdays=6,
    )
    session.flush()

    board = session.query(BoardExpectation).filter_by(club_id=1).first()
    assert board.ultimatum_active is True


def test_match_result_affects_board_confidence(setup_db):
    """Unexpected loss should reduce board confidence."""
    from fm.core.consequence_engine import ConsequenceEngine
    from fm.db.models import BoardExpectation

    session = setup_db
    board_before = session.query(BoardExpectation).filter_by(club_id=1).first()
    conf_before = board_before.board_confidence

    engine = ConsequenceEngine(session)
    engine._handle_match_result(
        "match_result", club_id=1, home_goals=0, away_goals=3, is_home=True,
        expected_result="win", matchday=5, season=2024,
    )
    session.flush()

    board_after = session.query(BoardExpectation).filter_by(club_id=1).first()
    assert board_after.board_confidence < conf_before
