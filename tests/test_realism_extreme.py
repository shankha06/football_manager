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
from fm.engine.match_engine import AdvancedMatchEngine
from fm.engine.match_state import MatchState, PlayerInMatch
from fm.engine.match_context import MatchContext, build_match_context
from fm.engine.tactics import TacticalContext
from fm.engine.resolver import resolve_pass, resolve_shot

def test_performance_sabotage_loop():
    print("\n--- [Extreme Test] Performance Sabotage Loop ---")
    
    # 1. Setup a mutinous context
    ctx = MatchContext()
    ctx.home_influence_morale = 15.0 # Mutinous
    ctx.away_influence_morale = 75.0 # Stable
    
    penalty_h = ctx.performance_sabotage_penalty("home")
    penalty_a = ctx.performance_sabotage_penalty("away")
    
    print(f"Home Sabotage Penalty (Morale 20): {penalty_h:.4f}")
    print(f"Away Sabotage Penalty (Morale 75): {penalty_a:.4f}")
    
    assert penalty_h > 0.10, "Mutinous morale should trigger a significant sabotage penalty."
    assert penalty_a == 0.0, "Stable morale should have zero sabotage penalty."
    
    # 2. Verify attribute degradation in resolver
    p = PlayerInMatch(player_id=1, name="Unhappy", position="ST", side="home")
    p.vision = 80
    p.composure = 80
    p.short_passing = 80
    p.passing = 80
    
    tactics = TacticalContext()
    
    # Run trials: standard vs sabotaged
    def run_trials(pen):
        successes = 0
        for _ in range(5000):
            res = resolve_pass(p, p, None, 1.0, tactics, sabotage_penalty=pen)
            if res.success:
                successes += 1
        return successes / 5000.0

    rate_stable = run_trials(0.0)
    rate_sabotaged = run_trials(penalty_h)
    
    print(f"Pass Success Rate (Stable): {rate_stable:.4f}")
    print(f"Pass Success Rate (Sabotaged): {rate_sabotaged:.4f}")
    
    assert rate_sabotaged < rate_stable - 0.05, "Sabotage penalty should noticeably degrade performance."
    print("✅ Performance Sabotage Loop Verified!")

def test_social_cluster_contagion():
    print("\n--- [Extreme Test] Social Cluster Contagion ---")
    session = MagicMock()
    club_id = 1
    
    # Create a squad with a specific nationality clique
    players = []
    for i in range(12):
        p = Player(
            id=i+1,
            name=f"Player {i+1}",
            nationality="Brazil" if i < 4 else "England", # 4 Brazilians
            age=25,
            overall=70,
            morale=70.0,
            club_id=club_id
        )
        players.append(p)
        
    session.query.return_value.filter_by.return_value.all.return_value = players
    
    dynamics = DynamicsManager(session)
    
    # Set one Brazilian as a Team Leader and make him MUTINOUS
    def mock_hierarchy(*args):
        h = {i: InfluenceLevel.OTHER for i in range(1, 13)}
        h[1] = InfluenceLevel.TEAM_LEADER # Brazilian Leader
        return h
        
    with patch.object(DynamicsManager, 'calculate_hierarchy', side_effect=mock_hierarchy):
        players[0].morale = 10.0 # Mutinous Leader
        
        # Week 1 contagion
        dynamics.update_morale_contagion(club_id)
        
        brazilians = [p for p in players if p.nationality == "Brazil" and p.id != 1]
        english = [p for p in players if p.nationality == "England"]
        
        avg_br = sum(p.morale for p in brazilians) / len(brazilians)
        avg_en = sum(p.morale for p in english) / len(english)
        
        print(f"Avg Morale (Brazil Clique) after 1 week: {avg_br:.2f}")
        print(f"Avg Morale (English Others) after 1 week: {avg_en:.2f}")
        
        # Clique should be hit harder because of social amplification from their leader
        assert avg_br < avg_en, "Social clustering should amplify contagion within the clique."
        print("✅ Social Cluster Contagion Verified!")

def test_contract_standoff_saga():
    print("\n--- [Extreme Test] Contract Standoff Saga ---")
    session = MagicMock()
    season_year = 2026
    
    # Setup a star with expiring contract
    star = Player(id=1, name="Star Man", overall=85, contract_expiry=2026, club_id=1, morale=70.0, loyalty_to_manager=50.0)
    star.club = MagicMock()
    star.club.name = "Giant FC"
    
    session.query.return_value.filter.return_value.filter.return_value.filter.return_value.all.return_value = [star]
    session.query.return_value.filter_by.return_value.first.return_value = None
    session.query.return_value.get.return_value = star
    
    narrative = NarrativeEngine(session)
    
    # 1. Trigger
    with patch('random.random', return_value=0.01):
        narrative._trigger_new_sagas(season_year, 1)
        
    added_objs = [call.args[0] for call in session.add.call_args_list]
    saga = [o for o in added_objs if isinstance(o, Saga) and o.type == "contract_standoff"][0]
    session.query.return_value.filter_by.return_value.all.return_value = [saga]
    
    print(f"Saga triggered: {saga.type}, Stage: {saga.stage}")
    
    # 2. Advance to Stage 2 (Agent demands)
    with patch('random.random', return_value=0.01):
        narrative._advance_existing_sagas(season_year, 2)
    print(f"Stage after advance: {saga.stage}")
    assert saga.stage == 2
    
    # 3. Advance to Stage 3 (Training boycott)
    initial_morale = star.morale
    with patch('random.random', return_value=0.01):
        narrative._advance_existing_sagas(season_year, 3)
    print(f"Stage after boycott: {saga.stage}, Morale: {star.morale}")
    
    assert saga.stage == 3
    assert star.morale < initial_morale - 20, "Training boycott should CRASH morale."
    print("✅ Contract Standoff Saga Verified!")

if __name__ == "__main__":
    try:
        test_performance_sabotage_loop()
        test_social_cluster_contagion()
        test_contract_standoff_saga()
        print("\n✨ ALL EXTREME REALISM TESTS PASSED ✨")
    except AssertionError as e:
        print(f"\n❌ EXTREME TEST ASSERTION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ EXTREME TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
