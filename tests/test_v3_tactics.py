"""Tactical interaction tests for the V3 transition calculator.

Verifies that tactical settings properly shift transition probabilities
in the expected directions.
"""
from __future__ import annotations

import random

import pytest

from fm.engine.chain_states import ChainState
from fm.engine.tactics import TacticalContext
from fm.engine.transition_calculator import BASE_TRANSITIONS, TransitionCalculator

random.seed(42)

# Default team attributes (average side)
DEFAULT_ATTRS = {"def_avg": 65.0, "mid_avg": 65.0, "att_avg": 65.0}
DEFAULT_CTX = {"momentum": 0.0, "fatigue_avg": 85.0, "morale": 0.0}
DEFAULT_ZONE = {}  # empty zone control (defaults to 0.5)


def _build(tactics, opponent=None, attrs=None, ctx=None, zone=None):
    """Build a transition matrix with the given tactical setup."""
    calc = TransitionCalculator()
    return calc.build_matrix(
        attrs or DEFAULT_ATTRS,
        tactics,
        ctx or DEFAULT_CTX,
        zone or DEFAULT_ZONE,
        opponent_tactics=opponent,
    )


class TestHighPressInteraction:
    """High press opponent vs short passing team should increase press triggers."""

    def test_high_press_vs_short_passing_increases_turnovers(self):
        short_pass = TacticalContext(passing_style="short")
        high_press_opp = TacticalContext(pressing="very_high")

        m_normal = _build(TacticalContext(), opponent=TacticalContext())
        m_pressed = _build(short_pass, opponent=high_press_opp)

        base_trigger = m_normal[ChainState.BUILDUP_DEEP].get(ChainState.PRESS_TRIGGERED, 0)
        pressed_trigger = m_pressed[ChainState.BUILDUP_DEEP].get(ChainState.PRESS_TRIGGERED, 0)

        assert pressed_trigger > base_trigger, (
            f"PRESS_TRIGGERED should increase: {pressed_trigger:.4f} vs {base_trigger:.4f}"
        )


class TestCounterAttack:
    """Counter-attack tactic with opponent high line should boost counter paths."""

    def test_counter_attack_exploits_high_line(self):
        counter = TacticalContext(counter_attack=True)
        high_line_opp = TacticalContext(defensive_line="high")

        m_base = _build(TacticalContext())
        m_counter = _build(counter, opponent=high_line_opp)

        base_ca = m_base[ChainState.TRANSITION].get(ChainState.COUNTER_ATTACK, 0)
        counter_ca = m_counter[ChainState.TRANSITION].get(ChainState.COUNTER_ATTACK, 0)

        assert counter_ca > base_ca, (
            f"COUNTER_ATTACK from TRANSITION should increase: {counter_ca:.4f} vs {base_ca:.4f}"
        )


class TestWidePlay:
    """Wide play vs narrow defence should produce more crosses."""

    def test_wide_play_vs_narrow_defense_more_crosses(self):
        wide = TacticalContext(width="very_wide")
        narrow_opp = TacticalContext(width="very_narrow")

        m_base = _build(TacticalContext())
        m_wide = _build(wide, opponent=narrow_opp)

        base_cross = m_base[ChainState.CHANCE_CREATION].get(ChainState.CROSS, 0)
        wide_cross = m_wide[ChainState.CHANCE_CREATION].get(ChainState.CROSS, 0)

        assert wide_cross > base_cross, (
            f"CROSS should increase: {wide_cross:.4f} vs {base_cross:.4f}"
        )


class TestDirectPassing:
    """Direct passing should increase LONG_BALL transitions."""

    def test_direct_passing_more_long_balls(self):
        direct = TacticalContext(passing_style="very_direct")

        m_base = _build(TacticalContext())
        m_direct = _build(direct)

        base_lb = m_base[ChainState.BUILDUP_MID].get(ChainState.LONG_BALL, 0)
        direct_lb = m_direct[ChainState.BUILDUP_MID].get(ChainState.LONG_BALL, 0)

        assert direct_lb > base_lb, (
            f"LONG_BALL should increase: {direct_lb:.4f} vs {base_lb:.4f}"
        )


class TestLowBlock:
    """Opponent with deep defensive line should reduce progression."""

    def test_low_block_reduces_opponent_progression(self):
        normal = TacticalContext()
        deep_opp = TacticalContext(defensive_line="deep")

        m_base = _build(normal, opponent=TacticalContext())
        m_blocked = _build(normal, opponent=deep_opp)

        base_prog = m_base[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)
        blocked_prog = m_blocked[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)

        assert blocked_prog < base_prog, (
            f"PROGRESSION should decrease vs low block: {blocked_prog:.4f} vs {base_prog:.4f}"
        )


class TestAttackingMentality:
    """Attacking mentality should increase CHANCE_CREATION -> SHOT."""

    def test_attacking_mentality_more_shots(self):
        attacking = TacticalContext(mentality="very_attacking")

        m_base = _build(TacticalContext())
        m_att = _build(attacking)

        base_shot = m_base[ChainState.CHANCE_CREATION].get(ChainState.SHOT, 0)
        att_shot = m_att[ChainState.CHANCE_CREATION].get(ChainState.SHOT, 0)

        assert att_shot > base_shot, (
            f"SHOT from CHANCE_CREATION should increase: {att_shot:.4f} vs {base_shot:.4f}"
        )


class TestDefensiveMentality:
    """Defensive mentality should not increase turnovers from buildup."""

    def test_defensive_mentality_fewer_turnovers(self):
        defensive = TacticalContext(mentality="very_defensive")

        m_base = _build(TacticalContext())
        m_def = _build(defensive)

        base_to = m_base[ChainState.BUILDUP_MID].get(ChainState.TURNOVER, 0)
        def_to = m_def[ChainState.BUILDUP_MID].get(ChainState.TURNOVER, 0)

        assert def_to <= base_to, (
            f"TURNOVER should not increase with defensive mentality: {def_to:.4f} vs {base_to:.4f}"
        )


class TestPlayOutFromBack:
    """play_out_from_back should shift GOAL_KICK transitions."""

    def test_play_out_from_back_changes_goal_kick(self):
        pofb = TacticalContext(play_out_from_back=True)

        m_base = _build(TacticalContext())
        m_pofb = _build(pofb)

        base_deep = m_base[ChainState.GOAL_KICK].get(ChainState.BUILDUP_DEEP, 0)
        pofb_deep = m_pofb[ChainState.GOAL_KICK].get(ChainState.BUILDUP_DEEP, 0)
        base_lb = m_base[ChainState.GOAL_KICK].get(ChainState.LONG_BALL, 0)
        pofb_lb = m_pofb[ChainState.GOAL_KICK].get(ChainState.LONG_BALL, 0)

        assert pofb_deep > base_deep, (
            f"BUILDUP_DEEP from GOAL_KICK should increase: {pofb_deep:.4f} vs {base_deep:.4f}"
        )
        assert pofb_lb < base_lb, (
            f"LONG_BALL from GOAL_KICK should decrease: {pofb_lb:.4f} vs {base_lb:.4f}"
        )


class TestZoneOverload:
    """High midfield zone control (>0.6) should boost progression."""

    def test_zone_overload_boosts_progression(self):
        # Zone control > 0.6 in midfield zones (cols 2-3)
        high_mid = {(c, r): 0.7 for c in (2, 3) for r in (0, 1, 2)}
        low_mid = {(c, r): 0.4 for c in (2, 3) for r in (0, 1, 2)}

        m_high = _build(TacticalContext(), zone=high_mid)
        m_low = _build(TacticalContext(), zone=low_mid)

        high_prog = m_high[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)
        low_prog = m_low[ChainState.BUILDUP_MID].get(ChainState.PROGRESSION, 0)

        assert high_prog > low_prog, (
            f"PROGRESSION should be higher with zone control: {high_prog:.4f} vs {low_prog:.4f}"
        )


class TestMatrixNormalization:
    """All matrix rows should sum to ~1.0 for random tactical configs."""

    def test_all_matrix_rows_sum_to_one(self):
        random.seed(42)
        mentalities = ["very_defensive", "defensive", "balanced", "attacking", "very_attacking"]
        pressings = ["low", "standard", "high", "very_high"]
        passing_styles = ["very_short", "short", "mixed", "direct", "very_direct"]
        widths = ["very_narrow", "narrow", "normal", "wide", "very_wide"]

        for _ in range(20):
            t = TacticalContext(
                mentality=random.choice(mentalities),
                pressing=random.choice(pressings),
                passing_style=random.choice(passing_styles),
                width=random.choice(widths),
                counter_attack=random.choice([True, False]),
                play_out_from_back=random.choice([True, False]),
                defensive_line=random.choice(["deep", "normal", "high"]),
            )
            opp = TacticalContext(
                mentality=random.choice(mentalities),
                pressing=random.choice(pressings),
                defensive_line=random.choice(["deep", "normal", "high"]),
                width=random.choice(widths),
            )
            matrix = _build(t, opponent=opp)
            for state, row in matrix.items():
                row_sum = sum(row.values())
                assert abs(row_sum - 1.0) < 0.01, (
                    f"Row {state} sums to {row_sum:.6f}, expected ~1.0"
                )
