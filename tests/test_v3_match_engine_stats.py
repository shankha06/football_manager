import pytest
from fm.engine.match_state import PlayerInMatch
from fm.engine.transition_calculator import TransitionCalculator
from fm.engine.tactics import TacticalContext
from fm.engine.resolver_v3 import resolve_shot_v3
from fm.engine.chain_states import ChainState

def test_midfield_attribute_impact():
    """Verify that higher midfield attributes increase progression probability."""
    calc = TransitionCalculator()
    tactics = TacticalContext()
    
    low_attrs = {"def_avg": 50, "mid_avg": 30, "att_avg": 50}
    high_attrs = {"def_avg": 50, "mid_avg": 85, "att_avg": 50}
    
    matrix_low = calc.build_matrix(low_attrs, tactics, {}, {})
    matrix_high = calc.build_matrix(high_attrs, tactics, {}, {})
    
    prob_low = matrix_low[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)
    prob_high = matrix_high[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)
    
    # We expect higher midfield to have higher progression probability
    assert prob_high > prob_low
    assert prob_high - prob_low > 0.05  # At least 5% delta

def test_shot_conversion_impact():
    """Verify that elite finishing/composure significantly out-converts weak attributes."""
    tactics = TacticalContext()
    shooter_weak = PlayerInMatch(player_id=1, name="Weak Striker", position="ST", side="home", finishing=40, composure=40)
    shooter_elite = PlayerInMatch(player_id=2, name="Elite Striker", position="ST", side="home", finishing=92, composure=88)
    gk = PlayerInMatch(player_id=10, name="Solid GK", position="GK", side="away", gk_reflexes=75, gk_diving=70)
    
    trials = 500
    goals_weak = 0
    goals_elite = 0
    
    for _ in range(trials):
        res_weak = resolve_shot_v3(shooter_weak, gk, None, 4, 1, tactics)
        if res_weak.success: goals_weak += 1
        
        res_elite = resolve_shot_v3(shooter_elite, gk, None, 4, 1, tactics)
        if res_elite.success: goals_elite += 1
        
    rate_weak = goals_weak / trials
    rate_elite = goals_elite / trials
    
    # Elite should be significantly better
    assert rate_elite > rate_weak
    assert rate_elite - rate_weak > 0.05

def test_fatigue_impact():
    """Verify that fatigue increases turnover probability."""
    calc = TransitionCalculator()
    tactics = TacticalContext()
    
    tired_ctx = {"fatigue_avg": 55.0}
    fresh_ctx = {"fatigue_avg": 100.0}
    
    matrix_tired = calc.build_matrix({"def_avg": 50, "mid_avg": 50, "att_avg": 50}, tactics, tired_ctx, {})
    matrix_fresh = calc.build_matrix({"def_avg": 50, "mid_avg": 50, "att_avg": 50}, tactics, fresh_ctx, {})
    
    turnover_tired = matrix_tired[ChainState.BUILDUP_MID].get(ChainState.TURNOVER, 0)
    turnover_fresh = matrix_fresh[ChainState.BUILDUP_MID].get(ChainState.TURNOVER, 0)
    
    # Tired players should have more turnovers
    assert turnover_tired > turnover_fresh

def test_tactical_mentality_impact():
    """Verify that mentality shifts basic progression probabilities."""
    calc = TransitionCalculator()
    attrs = {"def_avg": 50, "mid_avg": 50, "att_avg": 50}
    
    tac_defensive = TacticalContext(mentality="defensive")
    tac_attacking = TacticalContext(mentality="attacking")
    
    matrix_def = calc.build_matrix(attrs, tac_defensive, {}, {})
    matrix_att = calc.build_matrix(attrs, tac_attacking, {}, {})
    
    # Defensive mentality should favor safety/buildup over direct progression at midfield
    prog_def = matrix_def[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)
    prog_att = matrix_att[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)
    
    # The delta might be subtle but detectable
    assert prog_def != prog_att
