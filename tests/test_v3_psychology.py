"""Psychology engine detailed tests.

Covers momentum, snowball, crowd pressure, big-match temperament,
late-game determination, and team talk effects.
"""
from __future__ import annotations

import random

import pytest

from fm.engine.match_state import PlayerInMatch
from fm.engine.psychology import PsychologyEngine

random.seed(42)


def _make_player(side="home", **overrides) -> PlayerInMatch:
    """Create a minimal PlayerInMatch with optional attribute overrides."""
    defaults = dict(
        player_id=1, name="Test Player", position="ST", side=side,
        composure=70, big_match=65, temperament=60, professionalism=70,
    )
    defaults.update(overrides)
    return PlayerInMatch(**defaults)


# ---------------------------------------------------------------------------
# Momentum tests
# ---------------------------------------------------------------------------


class TestGoalMomentum:
    """After a goal, the scoring side's momentum should spike."""

    def test_goal_momentum_spike(self):
        eng = PsychologyEngine()
        eng.process_event("goal", "home", 30)
        assert eng.momentum["home"] > 0.2, (
            f"Home momentum {eng.momentum['home']:.3f} should be > 0.2 after goal"
        )


class TestMomentumDecay:
    """After decay calls, momentum should approach 0."""

    def test_momentum_decays_over_time(self):
        eng = PsychologyEngine()
        eng.process_event("goal", "home", 30)
        initial = eng.momentum["home"]
        for _ in range(20):
            eng.decay_momentum()
        assert eng.momentum["home"] < initial * 0.3, (
            f"Momentum should decay significantly: {eng.momentum['home']:.3f}"
        )


class TestRedCardMomentum:
    """Red card should give negative momentum to the receiving side."""

    def test_red_card_negative_momentum(self):
        eng = PsychologyEngine()
        eng.process_event("red_card", "home", 50)
        assert eng.momentum["home"] < 0, (
            f"Home momentum {eng.momentum['home']:.3f} should be < 0 after red card"
        )


# ---------------------------------------------------------------------------
# Snowball bonus
# ---------------------------------------------------------------------------


class TestSnowballBonus:
    """Snowball bonus should be active shortly after a goal and decay."""

    def test_snowball_bonus_active_after_goal(self):
        eng = PsychologyEngine()
        eng.process_event("goal", "home", 30)

        bonus_at_0 = eng.get_snowball_bonus("home", 30)
        bonus_at_3 = eng.get_snowball_bonus("home", 33)
        bonus_at_6 = eng.get_snowball_bonus("home", 36)

        assert bonus_at_0 > 0, f"Bonus at minute 30 should be > 0: {bonus_at_0}"
        assert bonus_at_3 > 0, f"Bonus at minute 33 should be > 0: {bonus_at_3}"
        assert bonus_at_6 == 0, f"Bonus at minute 36 should be 0: {bonus_at_6}"


# ---------------------------------------------------------------------------
# Crowd pressure
# ---------------------------------------------------------------------------


class TestCrowdPressure:
    """Home crowd should give positive modifier, away should give negative."""

    def test_crowd_pressure_home_vs_away(self):
        eng = PsychologyEngine()
        home_mod = eng.get_crowd_pressure("home", is_home=True, importance=1.0)
        away_mod = eng.get_crowd_pressure("away", is_home=False, importance=1.0)

        assert home_mod > 0, f"Home crowd pressure should be positive: {home_mod}"
        assert away_mod < 0, f"Away crowd pressure should be negative: {away_mod}"


# ---------------------------------------------------------------------------
# Individual modifiers
# ---------------------------------------------------------------------------


class TestBigMatchAnxiety:
    """Low big_match player in a big match should get composure penalty."""

    def test_big_match_anxiety_low_temperament(self):
        eng = PsychologyEngine()
        player = _make_player(big_match=25)
        mods = eng.get_individual_modifier(player, minute=30, importance=1.3)
        assert mods.get("composure_mod", 0) < 0, (
            f"Low big-match player should get composure penalty: {mods}"
        )


class TestBigMatchBoost:
    """High big_match player in a big match should get composure boost."""

    def test_big_match_boost_high_temperament(self):
        eng = PsychologyEngine()
        player = _make_player(big_match=90)
        mods = eng.get_individual_modifier(player, minute=30, importance=1.3)
        assert mods.get("composure_mod", 0) > 0, (
            f"High big-match player should get composure boost: {mods}"
        )


class TestLateGameDetermination:
    """At minute 85, losing, player should get determination bonus."""

    def test_late_game_determination_bonus(self):
        eng = PsychologyEngine()
        # Set momentum negative (losing)
        eng.momentum["home"] = -0.20
        player = _make_player(side="home", composure=80)
        mods = eng.get_individual_modifier(player, minute=85, importance=1.0)
        assert mods.get("determination_bonus", 0) > 0, (
            f"Losing at 85 min should give determination bonus: {mods}"
        )


# ---------------------------------------------------------------------------
# Team talks
# ---------------------------------------------------------------------------


class TestTeamTalkMotivate:
    """'motivate' talk should boost morale."""

    def test_team_talk_motivate_boosts_morale(self):
        eng = PsychologyEngine()
        player = _make_player()
        initial_morale = player.morale_mod
        eng.apply_team_talk_effects([player], "motivate")
        assert player.morale_mod > initial_morale, (
            f"Morale should increase after motivate: {player.morale_mod} vs {initial_morale}"
        )


class TestTeamTalkCriticize:
    """'criticize' on low temperament player should reduce morale."""

    def test_team_talk_criticize_can_backfire(self):
        eng = PsychologyEngine()
        player = _make_player(temperament=30)
        initial_morale = player.morale_mod
        eng.apply_team_talk_effects([player], "criticize")
        assert player.morale_mod < initial_morale, (
            f"Morale should drop for low-temperament player: {player.morale_mod} vs {initial_morale}"
        )


# ---------------------------------------------------------------------------
# Compound momentum
# ---------------------------------------------------------------------------


class TestMultipleGoalsMomentum:
    """Two goals for same side should compound momentum beyond single goal."""

    def test_multiple_goals_compound_momentum(self):
        eng1 = PsychologyEngine()
        eng1.process_event("goal", "home", 30)
        single_goal_momentum = eng1.momentum["home"]

        eng2 = PsychologyEngine()
        eng2.process_event("goal", "home", 30)
        eng2.process_event("goal", "home", 32)
        double_goal_momentum = eng2.momentum["home"]

        assert double_goal_momentum > single_goal_momentum, (
            f"Two goals momentum ({double_goal_momentum:.3f}) should exceed "
            f"single goal ({single_goal_momentum:.3f})"
        )


class TestConcedingReducesMomentum:
    """Scoring then conceding should reduce momentum compared to just scoring."""

    def test_conceding_reduces_momentum(self):
        eng1 = PsychologyEngine()
        eng1.process_event("goal", "home", 30)
        score_only = eng1.momentum["home"]

        eng2 = PsychologyEngine()
        eng2.process_event("goal", "home", 30)
        eng2.process_event("goal", "away", 35)
        score_then_concede = eng2.momentum["home"]

        assert score_then_concede < score_only, (
            f"Conceding should reduce momentum: {score_then_concede:.3f} vs {score_only:.3f}"
        )
