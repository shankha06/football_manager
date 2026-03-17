import sys
import os
from unittest.mock import MagicMock
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.join(os.path.dirname(__file__), ".."))))

from fm.db.models import Player, Saga, NewsItem
from fm.world.news_engine import NarrativeEngine

def test_saga_triggering():
    print("\n--- Testing Narrative Saga Triggering ---")
    session = MagicMock()
    
    # 1. Setup an unhappy star
    p = Player(id=1, name="Unhappy Star", short_name="Star", morale=20.0, overall=85, club_id=10)
    p.club = MagicMock()
    p.club.name = "Test FC"
    
    session.query(Player).filter().filter().filter().all.return_value = [p]
    session.query(Saga).filter_by().first.return_value = None # No existing saga
    
    engine = NarrativeEngine(session)
    
    # Run trigger loop (with mock random to force trigger)
    import random
    random.seed(42) # Should trigger given our logic if seed is right
    
    # Force random.random() < 0.2 to be true
    random.random = MagicMock(return_value=0.1)
    
    engine._trigger_new_sagas(2026, 10)
    
    # Verify Saga was added
    # session.add() should be called with a Saga object
    added_objs = [call.args[0] for call in session.add.call_args_list]
    sagas = [o for o in added_objs if isinstance(o, Saga)]
    news = [o for o in added_objs if isinstance(o, NewsItem)]
    
    print(f"Sagas created: {len(sagas)}")
    print(f"News created: {len(news)}")
    
    assert len(sagas) >= 1, "Should have created at least one saga"
    assert any(s.type == "transfer_unrest" for s in sagas), "Should include a transfer saga"
    assert len(news) >= 1, "Should have created news for the saga"
    print("✅ Saga triggering verified!")

def test_saga_progression():
    print("\n--- Testing Narrative Saga Progression ---")
    session = MagicMock()
    
    p = Player(id=1, name="Unhappy Star", short_name="Star", morale=20.0, club_id=10)
    p.club = MagicMock()
    p.club.name = "Test FC"
    
    # mock player retrieval
    session.query(Player).get.return_value = p
    
    # existing saga at stage 1
    saga = Saga(id=5, type="transfer_unrest", target_id=1, stage=1, is_active=True, data=json.dumps({"player_name": "Star"}))
    
    session.query(Saga).filter_by().all.return_value = [saga]
    
    engine = NarrativeEngine(session)
    
    # Force progression Stage 1 -> 2
    import random
    random.random = MagicMock(return_value=0.1) 
    
    engine._advance_existing_sagas(2026, 11)
    
    print(f"Saga stage after advancement: {saga.stage}")
    assert saga.stage == 2, "Saga should have progressed to stage 2"
    
    # Force progression Stage 2 -> 3
    random.random = MagicMock(return_value=0.1)
    engine._advance_existing_sagas(2026, 12)
    
    print(f"Saga stage after second advancement: {saga.stage}")
    assert saga.stage == 3, "Saga should have progressed to stage 3"
    assert p.wants_transfer == True, "Player should have handed in transfer request"
    print("✅ Saga progression verified!")

if __name__ == "__main__":
    try:
        test_saga_triggering()
        test_saga_progression()
        print("\n✨ ALL NARRATIVE ENGINE TESTS PASSED ✨")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
