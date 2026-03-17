import pytest
import random
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fm.db.models import Base, Player, Club, PlayerRelationship, NewsItem, BoardExpectation, TacticalSetup
from fm.core.match_situations import MatchSituationEngine

@pytest.fixture
def session():
    """Create an in-memory SQLite DB for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()
    
    # Seed data
    club = Club(id=1, name="Impact United", team_spirit=65.0)
    db_session.add(club)
    
    board = BoardExpectation(club_id=1, season=2024, board_confidence=60.0, fan_happiness=60.0)
    db_session.add(board)
    
    # Striker
    marco = Player(id=2, name="Marco", short_name="Marco", age=24, position="ST", club_id=1, 
                  finishing=88, composure=85, morale=65.0, form=65.0, overall=82)
    db_session.add(marco)
    
    # Friend of striker
    leo = Player(id=3, name="Leo", short_name="Leo", age=23, position="CAM", club_id=1,
                morale=65.0, form=65.0, overall=78)
    db_session.add(leo)
    
    # Captain
    gabriel = Player(id=4, name="Gabriel", short_name="Gabriel", age=29, position="CB", club_id=1,
                    trust_in_manager=75.0, overall=80)
    db_session.add(gabriel)
    
    # Relationships
    rel = PlayerRelationship(player_a_id=2, player_b_id=3, relationship_type="friends", strength=85) # High friendship between Marco and Leo
    db_session.add(rel)
    
    # Tactic (for captaincy)
    tac = TacticalSetup(club_id=1, captain_id=4)
    db_session.add(tac)
    
    db_session.commit()
    return db_session

def test_late_goal_morale_boost(session):
    """Verify morale increases after a late goal."""
    player = session.get(Player, 2)
    initial_morale = player.morale
    
    MatchSituationEngine.handle_late_goal(session, club_id=1, player_id=2, minute=89, is_comeback=True, season=2024, matchday=10)
    
    assert player.morale > initial_morale
    assert player.morale == pytest.approx(initial_morale + 8, rel=1e-2)
    
    # Check news
    news = session.query(NewsItem).filter_by(headline=f"DRAMA! Marco rescues Impact United in 90th minute").first()
    assert news is not None

def test_red_card_relationship_cascade(session):
    """Verify morale drops for friends when a player gets sent off."""
    marco = session.get(Player, 2)
    leo = session.get(Player, 3)
    initial_leo_morale = leo.morale
    
    MatchSituationEngine.handle_red_card_incident(session, club_id=1, player_id=2, incident_type="violent", minute=45, season=2024, matchday=11)
    
    # Leo should be sad because his friend Marco was sent off
    assert leo.morale < initial_leo_morale
    
    # Gabriel (Captain) should have a trust hit
    gabriel = session.get(Player, 4)
    assert gabriel.trust_in_manager < 75.0

def test_defensive_collapse_impact(session):
    """Verify team-wide morale hit after a defensive collapse."""
    MatchSituationEngine.handle_defensive_collapse(session, club_id=1, goals_conceded=3, time_window=15, season=2024, matchday=12)
    
    players = session.query(Player).filter_by(club_id=1).all()
    for p in players:
        # Everyone should have a morale hit
        assert p.morale < 65.0
    
    # Check news
    news = session.query(NewsItem).filter(NewsItem.headline.like("%collapse%")).first()
    assert news is not None
