import sys
import os
from unittest.mock import MagicMock

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fm.db.models import Player
from fm.world.dynamics import DynamicsManager, InfluenceLevel
from fm.engine.match_state import PlayerInMatch
from fm.engine.resolver import resolve_pass
from fm.engine.tactics import TacticalContext

def test_morale_contagion():
    print("\n--- Testing Morale Contagion ---")
    session = MagicMock()
    
    # Create a squad of 5 players
    # 2 leaders, 3 others
    p1 = Player(id=1, name="Leader 1", morale=90.0, overall=90, leadership=90, age=30)
    p2 = Player(id=2, name="Leader 2", morale=90.0, overall=85, leadership=85, age=31)
    p3 = Player(id=3, name="Commoner 1", morale=60.0, overall=40, leadership=40, age=20)
    p4 = Player(id=4, name="Commoner 2", morale=60.0, overall=40, leadership=40, age=21)
    p5 = Player(id=5, name="Commoner 3", morale=60.0, overall=40, leadership=40, age=22)
    
    players = [p1, p2, p3, p4, p5]
    session.query().filter_by().all.return_value = players
    
    dm = DynamicsManager(session)
    
    # Check hierarchy
    hierarchy = dm.calculate_hierarchy(1)
    print(f"Hierarchy counts: {list(hierarchy.values())}")
    assert hierarchy[1] == InfluenceLevel.TEAM_LEADER
    
    # Run contagion
    # With new weighted core: 2 TLs (90) + 3 HIs (60) 
    # Weighted avg = (90*2 + 60*1.5) / 3.5 = (180 + 90) / 3.5 = 77.14 < 80.
    # To get boost (>80):
    p3.morale = 80.0
    # New weighted avg = (180 + 40 + 30 + 30) / 3.5 = 280 / 3.5 = 80.0
    # Still needs to be > 80. Let's make them all 90.
    for p in players:
        p.morale = 90.0
    p3.morale = 60.0 # Target player stays low to see increase
    
    dm.update_morale_contagion(1)
    
    print(f"Commoner 1 Morale after contagion: {p3.morale}")
    assert p3.morale > 60.0, "Morale should have increased due to happy leaders and influential core"
    print("✅ Morale contagion verified!")

def test_chemistry_bonus_resolver():
    print("\n--- Testing Chemistry Bonus in Resolver ---")
    
    # Passer and Receiver are "Friends" (Strength 90)
    passer = PlayerInMatch(player_id=1, name="Passer", position="CM", side="home")
    receiver = PlayerInMatch(player_id=2, name="Receiver", position="ST", side="home")
    
    # High base attributes for stable testing
    passer.short_passing = 80
    passer.vision = 80
    passer.composure = 80
    passer.passing = 80
    passer.ball_control = 80
    
    # No partners
    passer.chemistry_partners = {}
    
    tactics = TacticalContext()
    
    # 1. Baseline without chemistry
    # resolve_pass uses random, so we'll mock or just observe high probability
    import random
    random.seed(42) # Deterministic for test
    
    # Check probability calculation logic (roughly)
    # base = 80
    # distance_penalty = 0
    # pressure = 0
    # tact_bonus = 0
    # success_chance = (80 / 99) = 0.808
    
    # 2. With Chemistry
    passer.chemistry_partners[2] = 100.0 # Max chemistry
    # chemistry_bonus = (1.0) * 0.08 = 0.08
    # total_chance = 0.808 + 0.08 = 0.888
    
    # We can't easily test the private success_chance without re-calculating it or 
    # running many trials. Let's do 1000 trials.
    
    def get_success_rate(partner_id=None):
        if partner_id:
            passer.chemistry_partners[2] = 100.0
        else:
            passer.chemistry_partners = {}
            
        successes = 0
        for _ in range(10000):
            res = resolve_pass(passer, receiver, None, 1.0, tactics)
            if res.success:
                successes += 1
        return successes / 10000.0

    rate_no_chem = get_success_rate(None)
    rate_with_chem = get_success_rate(2)
    
    print(f"Success Rate (No Chem): {rate_no_chem:.4f}")
    print(f"Success Rate (With Chem): {rate_with_chem:.4f}")
    
    assert rate_with_chem > rate_no_chem + 0.05, "Chemistry should significantly boost success rate"
    print("✅ Chemistry bonus verified in resolver!")

if __name__ == "__main__":
    try:
        test_morale_contagion()
        test_chemistry_bonus_resolver()
        print("\n✨ ALL SQUAD DYNAMICS TESTS PASSED ✨")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
