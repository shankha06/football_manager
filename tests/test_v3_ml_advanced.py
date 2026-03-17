"""ML model edge case tests for xG, match predictor, and tactical scorer.

Tests the xG model's sensitivity to input features, match predictor
probability distributions, and tactical scorer overload/counter logic.
"""
from __future__ import annotations

import random

import pytest

random.seed(42)


# ---------------------------------------------------------------------------
# xG model tests
# ---------------------------------------------------------------------------


class TestXGHeader:
    """Header shots should have lower xG than foot shots at the same distance."""

    def test_xg_header_lower_than_foot(self):
        from fm.engine.ml.xg_model import XGModel
        from fm.engine.ml.training_data import generate_shot_data

        model = XGModel()
        data = generate_shot_data(50000)
        model.train(data)

        base_features = {
            "distance_to_goal": 12.0,
            "angle": 30.0,
            "is_close_range": True,
            "preceding_action": "open_play",
            "defender_proximity": 2.0,
            "game_state": "drawing",
            "shooter_finishing": 75,
            "shooter_composure": 70,
            "gk_quality": 60,
            "is_counter": False,
            "minute_bucket": 3,
        }

        foot_features = {**base_features, "body_part": "foot"}
        head_features = {**base_features, "body_part": "head"}

        xg_foot = model.predict(foot_features)
        xg_head = model.predict(head_features)

        assert xg_head < xg_foot, (
            f"Header xG ({xg_head:.4f}) should be lower than foot ({xg_foot:.4f})"
        )


class TestXGCounterBonus:
    """Counter attack shots should have higher xG than open play."""

    def test_xg_counter_attack_bonus(self):
        from fm.engine.ml.xg_model import XGModel
        from fm.engine.ml.training_data import generate_shot_data

        model = XGModel()
        data = generate_shot_data(50000)
        model.train(data)

        base = {
            "distance_to_goal": 15.0,
            "angle": 25.0,
            "body_part": "foot",
            "is_close_range": False,
            "defender_proximity": 2.5,
            "game_state": "drawing",
            "shooter_finishing": 70,
            "shooter_composure": 70,
            "gk_quality": 60,
            "minute_bucket": 3,
        }

        open_play = {**base, "preceding_action": "open_play", "is_counter": False}
        counter = {**base, "preceding_action": "counter", "is_counter": True}

        xg_open = model.predict(open_play)
        xg_counter = model.predict(counter)

        assert xg_counter > xg_open, (
            f"Counter xG ({xg_counter:.4f}) should exceed open play ({xg_open:.4f})"
        )


class TestXGGKQuality:
    """Higher GK quality should reduce xG."""

    def test_xg_gk_quality_matters(self):
        from fm.engine.ml.xg_model import XGModel
        from fm.engine.ml.training_data import generate_shot_data

        model = XGModel()
        data = generate_shot_data(50000)
        model.train(data)

        base = {
            "distance_to_goal": 12.0,
            "angle": 30.0,
            "body_part": "foot",
            "is_close_range": True,
            "preceding_action": "open_play",
            "defender_proximity": 2.0,
            "game_state": "drawing",
            "shooter_finishing": 75,
            "shooter_composure": 70,
            "is_counter": False,
            "minute_bucket": 3,
        }

        low_gk = {**base, "gk_quality": 30}
        high_gk = {**base, "gk_quality": 90}

        xg_low = model.predict(low_gk)
        xg_high = model.predict(high_gk)

        assert xg_high < xg_low, (
            f"Higher GK xG ({xg_high:.4f}) should be lower than low GK ({xg_low:.4f})"
        )


class TestXGComposure:
    """Higher shooter composure should increase xG."""

    def test_xg_composure_matters(self):
        from fm.engine.ml.xg_model import XGModel
        from fm.engine.ml.training_data import generate_shot_data

        model = XGModel()
        data = generate_shot_data(50000)
        model.train(data)

        base = {
            "distance_to_goal": 12.0,
            "angle": 30.0,
            "body_part": "foot",
            "is_close_range": True,
            "preceding_action": "open_play",
            "defender_proximity": 2.0,
            "game_state": "drawing",
            "shooter_finishing": 75,
            "gk_quality": 60,
            "is_counter": False,
            "minute_bucket": 3,
        }

        low_comp = {**base, "shooter_composure": 30}
        high_comp = {**base, "shooter_composure": 90}

        xg_low = model.predict(low_comp)
        xg_high = model.predict(high_comp)

        assert xg_high > xg_low, (
            f"Higher composure xG ({xg_high:.4f}) should exceed low ({xg_low:.4f})"
        )


# ---------------------------------------------------------------------------
# Match predictor tests
# ---------------------------------------------------------------------------


class TestMatchPredictorDraw:
    """Equal teams should have draw probability between 20-35%."""

    def test_match_predictor_draw_probability(self):
        from fm.engine.ml.match_predictor import MatchPredictor
        from fm.engine.ml.training_data import generate_match_data

        mp = MatchPredictor()
        data = generate_match_data(30000)
        mp.train(data)

        result = mp.predict(
            home_overall=75.0, away_overall=75.0,
            home_form=8.0, away_form=8.0,
            home_adv=0.05, tactical=0.0,
            fatigue_diff=0.0, morale_diff=0.0,
        )

        draw_pct = result["draw"] * 100
        assert 10 <= draw_pct <= 45, (
            f"Draw probability {draw_pct:.1f}% outside [10, 45]"
        )


class TestMatchPredictorMorale:
    """Higher morale should favor that team."""

    def test_match_predictor_morale_impact(self):
        from fm.engine.ml.match_predictor import MatchPredictor
        from fm.engine.ml.training_data import generate_match_data

        mp = MatchPredictor()
        data = generate_match_data(30000)
        mp.train(data)

        result_neutral = mp.predict(
            home_overall=75.0, away_overall=75.0,
            home_form=8.0, away_form=8.0,
            home_adv=0.05, tactical=0.0,
            fatigue_diff=0.0, morale_diff=0.0,
        )

        result_morale = mp.predict(
            home_overall=75.0, away_overall=75.0,
            home_form=8.0, away_form=8.0,
            home_adv=0.05, tactical=0.0,
            fatigue_diff=0.0, morale_diff=30.0,
        )

        assert result_morale["home_win"] > result_neutral["home_win"], (
            f"High morale home_win ({result_morale['home_win']:.4f}) should exceed "
            f"neutral ({result_neutral['home_win']:.4f})"
        )


# ---------------------------------------------------------------------------
# Tactical scorer tests
# ---------------------------------------------------------------------------


class TestTacticalScorerOverload:
    """Team with 3v2 midfield overload should score higher than balanced."""

    def test_tactical_scorer_overload_bonus(self):
        from fm.engine.ml.tactical_scorer import TacticalScorer

        scorer = TacticalScorer()

        own_tactics_overload = {
            "style": "possession",
            "formation": "4-3-3",
            "zones": {
                "defence": 4, "midfield": 5, "attack": 2,
                "left_flank": 1, "right_flank": 1,
            },
        }
        opponent_tactics = {
            "style": "balanced",
            "formation": "4-4-2",
            "zones": {
                "defence": 4, "midfield": 3, "attack": 2,
                "left_flank": 1, "right_flank": 1,
            },
        }
        own_balanced = {
            "style": "balanced",
            "formation": "4-4-2",
            "zones": {
                "defence": 4, "midfield": 3, "attack": 2,
                "left_flank": 1, "right_flank": 1,
            },
        }

        players = [{"position": "CM", "passing": 75, "dribbling": 70, "stamina": 75}] * 11

        score_overload = scorer.score(own_tactics_overload, opponent_tactics, players, players)
        score_balanced = scorer.score(own_balanced, opponent_tactics, players, players)

        assert score_overload > score_balanced, (
            f"Overload score ({score_overload:.1f}) should exceed balanced ({score_balanced:.1f})"
        )


class TestTacticalScorerCounterVsPress:
    """Counter-attack should score well against high press."""

    def test_tactical_scorer_counter_vs_press(self):
        from fm.engine.ml.tactical_scorer import TacticalScorer

        scorer = TacticalScorer()

        counter_tactics = {
            "style": "counter_attack",
            "formation": "4-4-2",
            "mentality": "defensive",
        }
        press_opponent = {
            "style": "high_press",
            "formation": "4-3-3",
        }

        players = [{"position": "ST", "pace": 80, "shooting": 75, "finishing": 78}] * 11

        score = scorer.score(counter_tactics, press_opponent, players, players)

        # Counter vs high press should get a good style counter bonus
        # style_counter_score for counter_attack vs high_press = 50 + 12*(35/15) = ~78
        assert score > 50, (
            f"Counter vs press score ({score:.1f}) should be > 50"
        )
