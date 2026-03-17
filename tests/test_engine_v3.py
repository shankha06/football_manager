"""Tests for the V3 Markov chain match engine."""
import pytest
import random


def test_chain_states_enum():
    """All 17 chain states are defined."""
    from fm.engine.chain_states import ChainState, TERMINAL_STATES
    assert len(ChainState) == 17
    assert ChainState.GOAL in TERMINAL_STATES
    assert ChainState.TURNOVER in TERMINAL_STATES


def test_transition_matrix_sums_to_one():
    """Every row in the transition matrix sums to ~1.0."""
    from fm.engine.transition_calculator import TransitionCalculator, BASE_TRANSITIONS
    from fm.engine.chain_states import ChainState

    calc = TransitionCalculator()
    # Use base transitions
    for state, transitions in BASE_TRANSITIONS.items():
        total = sum(transitions.values())
        assert abs(total - 1.0) < 0.01, f"{state}: row sums to {total}"


def test_high_press_increases_turnover():
    """High pressing should increase BUILDUP_DEEP -> PRESS_TRIGGERED probability."""
    from fm.engine.transition_calculator import TransitionCalculator
    from fm.engine.chain_states import ChainState
    from fm.engine.tactics import TacticalContext

    calc = TransitionCalculator()
    base_tactics = TacticalContext(pressing="standard")
    high_press_tactics = TacticalContext(pressing="very_high")

    base_matrix = calc.build_matrix(
        team_attrs={"def_avg": 60, "mid_avg": 65, "att_avg": 70},
        tactics=base_tactics,
        match_context={"momentum": 0.0, "fatigue_avg": 85, "morale": 0.0},
        zone_control={},
    )
    high_matrix = calc.build_matrix(
        team_attrs={"def_avg": 60, "mid_avg": 65, "att_avg": 70},
        tactics=high_press_tactics,
        match_context={"momentum": 0.0, "fatigue_avg": 85, "morale": 0.0},
        zone_control={},
    )

    base_press = base_matrix[ChainState.BUILDUP_DEEP].get(ChainState.PRESS_TRIGGERED, 0)
    high_press = high_matrix[ChainState.BUILDUP_DEEP].get(ChainState.PRESS_TRIGGERED, 0)
    assert high_press > base_press, f"High press {high_press} should > base {base_press}"


def test_counter_vs_high_line_increases_counter():
    """Counter-attack enabled should boost counter probability from turnovers."""
    from fm.engine.transition_calculator import TransitionCalculator
    from fm.engine.chain_states import ChainState
    from fm.engine.tactics import TacticalContext

    calc = TransitionCalculator()
    counter_tactics = TacticalContext(counter_attack=True)
    no_counter = TacticalContext(counter_attack=False)

    opp_high_line = TacticalContext(defensive_line="high")

    counter_matrix = calc.build_matrix(
        team_attrs={"def_avg": 60, "mid_avg": 65, "att_avg": 70},
        tactics=counter_tactics,
        match_context={"momentum": 0.0, "fatigue_avg": 85, "morale": 0.0},
        zone_control={},
        opponent_tactics=opp_high_line,
    )
    base_matrix = calc.build_matrix(
        team_attrs={"def_avg": 60, "mid_avg": 65, "att_avg": 70},
        tactics=no_counter,
        match_context={"momentum": 0.0, "fatigue_avg": 85, "morale": 0.0},
        zone_control={},
    )

    # Check PRESS_TRIGGERED -> COUNTER_ATTACK
    counter_prob = counter_matrix.get(ChainState.PRESS_TRIGGERED, {}).get(ChainState.COUNTER_ATTACK, 0)
    base_prob = base_matrix.get(ChainState.PRESS_TRIGGERED, {}).get(ChainState.COUNTER_ATTACK, 0)
    assert counter_prob > base_prob


def test_momentum_spike_after_goal():
    """Psychology engine should spike momentum after a goal."""
    from fm.engine.psychology import PsychologyEngine

    psy = PsychologyEngine()
    initial = psy.momentum["home"]
    psy.process_event("goal", "home", 30)
    assert psy.momentum["home"] > initial + 0.2


def test_psychology_snowball_window():
    """Snowball bonus should be active within 5 minutes of a goal."""
    from fm.engine.psychology import PsychologyEngine

    psy = PsychologyEngine()
    psy.process_event("goal", "home", 30)
    bonus = psy.get_snowball_bonus("home", 33)
    assert bonus > 0.0
    # After 5+ minutes, should decay
    bonus_late = psy.get_snowball_bonus("home", 40)
    assert bonus_late < bonus


def test_psychology_big_match_anxiety():
    """Players with low big_match + high importance should get composure penalty."""
    from fm.engine.psychology import PsychologyEngine
    from fm.engine.match_state import PlayerInMatch

    psy = PsychologyEngine()
    anxious = PlayerInMatch(player_id=1, name="Test", position="ST", side="home", big_match=30)
    mods = psy.get_individual_modifier(anxious, minute=45, importance=1.2)
    assert mods.get("composure_mod", 0) < 0


class TestRealism:
    """Realism integration tests over many simulated matches."""

    @pytest.fixture(autouse=True)
    def setup(self):
        random.seed(42)

    def _make_players(self, side: str, overall: int = 70):
        """Create a basic 11-player squad."""
        from fm.engine.match_state import PlayerInMatch
        positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "LW", "RW", "CAM", "ST"]
        players = []
        for i, pos in enumerate(positions):
            p = PlayerInMatch(
                player_id=i + (0 if side == "home" else 100),
                name=f"{side}_{pos}_{i}",
                position=pos,
                side=side,
                overall=overall,
                is_gk=(pos == "GK"),
            )
            # Set all attrs to overall
            for attr in ["pace", "shooting", "finishing", "passing", "dribbling",
                        "defending", "physical", "composure", "reactions", "positioning",
                        "short_passing", "long_passing", "vision", "crossing",
                        "standing_tackle", "marking", "interceptions", "heading_accuracy",
                        "stamina", "strength", "agility", "balance", "ball_control",
                        "shot_power", "long_shots", "curve", "aggression", "jumping"]:
                setattr(p, attr, overall)
            if pos == "GK":
                for attr in ["gk_diving", "gk_handling", "gk_positioning", "gk_reflexes"]:
                    setattr(p, attr, overall)
            players.append(p)
        return players
