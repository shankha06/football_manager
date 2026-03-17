import sys
import os
import random
import json
from unittest.mock import MagicMock, patch

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), ".."))))

from fm.db.models import Player, Club, Season, Saga, NewsItem
from fm.world.dynamics import DynamicsManager, InfluenceLevel
from fm.world.news_engine import NarrativeEngine
from fm.engine.match_engine import AdvancedMatchEngine, PlayerDecisionEngine
from fm.engine.match_state import MatchState, PlayerInMatch
from fm.engine.tactics import TacticalContext
from fm.engine.roles import PlayerRole

def setup_mock_squad(session, club_id, n_players=20):
    players = []
    for i in range(n_players):
        p = Player(
            id=i+1,
            name=f"Player {i+1}",
            overall=random.randint(60, 90),
            leadership=random.randint(30, 80),
            age=random.randint(18, 35),
            morale=70.0,
            club_id=club_id
        )
        p.club = MagicMock()
        p.club.name = f"Club {club_id}"
        players.append(p)
    
    # Robust mock for session.query(Player).filter_by(club_id=club_id).all()
    session.query.return_value.filter_by.return_value.all.return_value = players
    return players

def test_systemic_morale_contagion():
    print("\n--- [Deep Test] Systemic Morale Contagion ---")
    session = MagicMock()
    club_id = 1
    players = setup_mock_squad(session, club_id)
    
    # Identify the Team Leaders
    dynamics = DynamicsManager(session)
    hierarchy = dynamics.calculate_hierarchy(club_id)
    leaders = [p for p in players if hierarchy[p.id] == InfluenceLevel.TEAM_LEADER]
    
    print(f"Initial Avg Morale: {sum(p.morale for p in players)/len(players):.2f}")
    
    # CRASH the core (Leaders + Highly Influential)
    for pid, level in hierarchy.items():
        if level in [InfluenceLevel.TEAM_LEADER, InfluenceLevel.HIGHLY_INFLUENTIAL]:
            p = next(player for player in players if player.id == pid)
            p.morale = 20.0
    
    # Simulate 5 weeks of contagion
    for week in range(5):
        # We need to ensure calculate_hierarchy also uses the mock
        dynamics.update_morale_contagion(club_id)
    
    avg_morale = sum(p.morale for p in players)/len(players)
    print(f"Avg Morale after 5 weeks of leader unrest: {avg_morale:.2f}")
    
    assert avg_morale < 65.0, "Morale contagion should have dragged down the squad average."
    print("✅ Systemic Morale Contagion Verified!")

def test_long_term_saga_stability():
    print("\n--- [Deep Test] Long-term Saga Continuity ---")
    session = MagicMock()
    season_year = 2026
    
    # Setup an unhappy star for a saga
    star = Player(id=100, name="Unhappy Star", morale=15.0, overall=88, club_id=1)
    star.club = MagicMock()
    star.club.name = "Giant FC"
    
    # Robust mock for the chain session.query(...).filter().filter().filter().all()
    session.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = [star]
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.query.return_value.get.return_value = star
    
    narrative = NarrativeEngine(session)
    
    # 1. Trigger the Saga
    with patch('random.random', return_value=0.01): # Force trigger
        narrative._trigger_new_sagas(season_year, 1)
    
    added_objs = [call.args[0] for call in session.add.call_args_list]
    sagas = [o for o in added_objs if isinstance(o, Saga)]
    if not sagas:
        print(f"DEBUG: Found {len(added_objs)} added objects, but no Saga.")
        for o in added_objs:
            print(f"  - {type(o)}")
        raise AssertionError("Should have created a transfer saga")
        
    saga = sagas[0]
    # Set the return value for the advancement queries
    session.query.return_value.filter_by.return_value.all.return_value = [saga]
    
    print(f"Saga started: {saga.type}, stage: {saga.stage}")
    
    # 2. Advance through stages over multiple matchdays
    for md in range(2, 6):
        with patch('random.random', return_value=0.01): # Force advance
            narrative._advance_existing_sagas(season_year, md)
    
    print(f"Saga stage after multiple matchdays: {saga.stage}")
    assert saga.stage == 3, f"Saga should have reached the final stage (Transfer Request), current: {saga.stage}"
    assert star.wants_transfer == True, "Logic Failure: Star should WANT TO LEAVE at stage 3."
    print("✅ Long-term Saga Continuity Verified!")

def test_tactical_role_distribution():
    print("\n--- [Deep Test] Tactical Role Positional Distribution ---")
    
    # Test if an Inverted Full-Back (LB) consistently occupies central zones over many possessions
    engine = AdvancedMatchEngine()
    h_tac = TacticalContext(roles=["IWB"] + ["CB"]*3 + ["CM"]*4 + ["ST"]*2)
    a_tac = TacticalContext() # Standard
    
    # Mock MatchState
    state = MatchState()
    state.ball_side = "home"
    
    home_players = [PlayerInMatch(player_id=i, name=f"P{i}", position="LB" if i==0 else "CH", side="home") for i in range(11)]
    away_players = [PlayerInMatch(player_id=i+11, name=f"P{i+11}", position="CH", side="away") for i in range(11)]
    
    state.home_players = home_players
    state.away_players = away_players
    
    col_history = []
    for _ in range(50):
        engine._assign_zones(state, h_tac, a_tac)
        iwb = home_players[0]
        col_history.append(iwb.zone_col)
    
    avg_col = sum(col_history) / len(col_history)
    print(f"IWB (LB) Average Column over 50 iterations: {avg_col:.2f} (Base LB should be 1)")
    
    assert avg_col > 1.5, "IWB should be consistently drifting toward more central columns (2-3)."
    print("✅ Tactical Role Positional Distribution Verified!")

def test_spatial_congestion():
    print("\n--- [Deep Test] Spatial Congestion Resilience ---")
    engine = AdvancedMatchEngine()
    
    # Setup a high-congestion tactic: 
    # slot 0 (LB) -> IWB (drifts to 3,1)
    # slot 4 (LM) -> IW (drifts to 4,1)
    # slot 8 (ST) -> F9 (drops to 4,1)
    # slot 5 (CM) -> AM (base 3,1)
    
    roles = ["IWB", "CB", "CB", "RB", "IW", "AM", "CM", "RM", "F9", "ST"]
    h_tac = TacticalContext(roles=roles)
    a_tac = TacticalContext()
    
    state = MatchState()
    state.ball_side = "home"
    
    home_players = [
        PlayerInMatch(player_id=i, name=f"P{i}", position="LB" if i==0 else "CH", side="home") 
        for i in range(11)
    ]
    state.home_players = home_players
    state.away_players = [PlayerInMatch(player_id=i+11, name=f"P{i+11}", position="CH", side="away") for i in range(11)]
    
    engine._assign_zones(state, h_tac, a_tac)
    
    # Check for overcrowding
    positions = [(p.zone_col, p.zone_row) for p in home_players if not p.is_gk]
    print(f"IWB position: {home_players[0].zone_col}, {home_players[0].zone_row}")
    print(f"IW position: {home_players[4].zone_col}, {home_players[4].zone_row}")
    print(f"F9 position: {home_players[8].zone_col}, {home_players[8].zone_row}")
    
    # In a real game, this causes "clashing", which our engine handles by simply allowing them to be in the zone,
    # but we want to verify the engine doesn't CRASH and each role still applies its offset.
    assert home_players[0].zone_col == 3 and home_players[0].zone_row == 1, "IWB failed to reach pocket"
    assert home_players[8].zone_col == 4, "F9 failed to drop deep"
    
    print("✅ Spatial Congestion Resilience Verified!")

def test_conflicting_leadership():
    print("\n--- [Deep Test] Conflicting Leadership Resolution ---")
    session = MagicMock()
    club_id = 1
    players = setup_mock_squad(session, club_id, n_players=10)
    
    # Setup: 2 Team Leaders, 1 Highly Influential
    # P1 (TL) = 10 (Mutinous)
    # P2 (TL) = 50 (Unhappy)
    # P3 (HI) = 30 (Very Unhappy)
    # Core Weighted Avg: (10*1 + 50*1 + 30*0.5) / 2.5 = 75 / 2.5 = 30
    # 30 < 40 -> Should trigger negative contagion.
    
    def mock_hierarchy(*args):
        return {
            1: InfluenceLevel.TEAM_LEADER, 
            2: InfluenceLevel.TEAM_LEADER,
            3: InfluenceLevel.HIGHLY_INFLUENTIAL,
            **{i: InfluenceLevel.OTHER for i in range(4, 11)}
        }
    
    with patch.object(DynamicsManager, 'calculate_hierarchy', side_effect=mock_hierarchy):
        dynamics = DynamicsManager(session)
        players[0].morale = 15.0
        players[1].morale = 50.0
        players[2].morale = 30.0
        
        # Commoners are players[3:] (indices 3 to 9)
        commoners = players[3:]
        initial_avg = sum(p.morale for p in commoners)/len(commoners)
        print(f"Initial Average Morale (Commoners): {initial_avg:.2f}")
        
        # Run contagion for 3 weeks
        for _ in range(3):
            dynamics.update_morale_contagion(club_id)
            
        final_avg = sum(p.morale for p in commoners)/len(commoners)
        print(f"Final Average Morale (Commoners): {final_avg:.2f}")
        
        assert final_avg < initial_avg, "The combined unrest of leaders and influencers should drag down the squad."
        print("✅ Conflicting Leadership Resolution Verified!")
        
    print("✅ Conflicting Leadership Resolution Verified!")

def test_saga_interruption():
    print("\n--- [Deep Test] Saga Interruption (Injury Pivot) ---")
    session = MagicMock()
    season_year = 2026
    
    # Setup a star in a transfer saga
    star = Player(id=100, name="Unhappy Star", morale=15.0, overall=88, club_id=1, injured_weeks=0)
    star.club = MagicMock()
    star.club.name = "Giant FC"
    
    session.query.return_value.get.return_value = star
    
    saga = Saga(
        type="transfer_unrest",
        target_id=star.id,
        club_id=star.club_id,
        stage=1,
        data=json.dumps({"player_name": star.name})
    )
    session.query.return_value.filter_by.return_value.all.return_value = [saga]
    
    narrative = NarrativeEngine(session)
    print(f"Saga active: {saga.type}, stage: {saga.stage}")
    
    # 1. Star gets long-term injury
    star.injured_weeks = 8
    print(f"Star suffers 8-week injury mid-saga.")
    
    # 2. Advance saga
    # Normally, if injured, the saga should either pause or terminate.
    # Let's verify that NarrativeEngine handles this (or we need to implement it).
    # Current implementation doesn't check injury, let's see what happens.
    narrative._advance_existing_sagas(season_year, 2)
    
    # If we haven't implemented injury-checks yet, this is a "failed" stress test that we should fix.
    # For now, let's assume we WANT it to terminate if injured.
    # Currently Saga.is_active is True.
    # Let's adjust narrative_engine.py to check for injuries if we find it doesn't.
    
    print(f"Saga status after injury advance: {saga.is_active}")
    assert saga.is_active == False, "Saga should have terminated due to long-term injury."
    print("✅ Saga Interruption Handling Verified!")

def test_chemistry_synergies():
    print("\n--- [Deep Test] Chemistry Synergies (Passing Triangles) ---")
    from fm.engine.resolver import resolve_pass
    
    # Setup 3 players in a triangle: P1 -> P2 -> P3 -> P1
    p1 = PlayerInMatch(player_id=1, name="P1", position="CM", side="home")
    p2 = PlayerInMatch(player_id=2, name="P2", position="ST", side="home")
    p3 = PlayerInMatch(player_id=3, name="P3", position="LW", side="home")
    
    for p in [p1, p2, p3]:
        p.short_passing = 80
        p.vision = 80
        p.composure = 80
        p.passing = 80
    
    tactics = TacticalContext()
    
    # Trace success rate of P1 -> P2 (isolated) vs P1 -> P2 (with P3 support/chemistry)
    def run_trials(p_from, p_to, chemistry=0):
        if chemistry > 0:
            p_from.chemistry_partners[p_to.player_id] = chemistry
        else:
            p_from.chemistry_partners = {}
            
        successes = 0
        for _ in range(5000):
            res = resolve_pass(p_from, p_to, None, 1.0, tactics)
            if res.success:
                successes += 1
        return successes / 5000.0

    rate_isolated = run_trials(p1, p2, 0)
    rate_chem_pair = run_trials(p1, p2, 100)
    
    print(f"Success Rate (Isolated): {rate_isolated:.4f}")
    print(f"Success Rate (Chemistry Pair): {rate_chem_pair:.4f}")
    
    assert rate_chem_pair > rate_isolated + 0.04, "Chemistry pair should boost success significantly."
    
    # Triangle synergy: If P1, P2, and P3 are all friends, does the ball circulate better?
    # Our current engine only checks the immediate pair.
    # But we can verify that the pair bonus is consistent.
    
    print("✅ Chemistry Synergies Verified!")

if __name__ == "__main__":
    try:
        test_systemic_morale_contagion()
        test_long_term_saga_stability()
        test_tactical_role_distribution()
        test_spatial_congestion()
        test_conflicting_leadership()
        test_saga_interruption()
        test_chemistry_synergies()
        print("\n✨ ALL DEEP REALISM TESTS PASSED ✨")
    except AssertionError as e:
        print(f"\n❌ DEEP TEST ASSERTION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ DEEP TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
