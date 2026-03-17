"""Tests for ML models (xG, match predictor, valuation)."""
import pytest
import numpy as np


class TestXGModel:
    """xG model should produce sensible predictions."""

    def test_close_range_higher_than_long_range(self):
        """Close-range central shots should have higher xG than long-range."""
        from fm.engine.ml.xg_model import XGModel
        model = XGModel()
        # Train if needed
        if not model.model:
            from fm.engine.ml.training_data import generate_shot_data
            data = generate_shot_data(10000)
            model.train(data)

        close = model.predict({
            "distance_to_goal": 6, "angle": 45, "body_part": "foot",
            "is_close_range": True, "preceding_action": "open_play",
            "defender_proximity": 2, "game_state": "drawing",
            "shooter_finishing": 80, "shooter_composure": 75,
            "gk_quality": 70, "is_counter": False, "minute_bucket": 2,
        })
        far = model.predict({
            "distance_to_goal": 30, "angle": 15, "body_part": "foot",
            "is_close_range": False, "preceding_action": "open_play",
            "defender_proximity": 3, "game_state": "drawing",
            "shooter_finishing": 80, "shooter_composure": 75,
            "gk_quality": 70, "is_counter": False, "minute_bucket": 2,
        })
        assert close > far, f"Close xG {close:.3f} should > far xG {far:.3f}"

    def test_xg_range(self):
        """xG should always be between 0 and 1."""
        from fm.engine.ml.xg_model import XGModel
        from fm.engine.ml.training_data import generate_shot_data
        model = XGModel()
        if not model.model:
            data = generate_shot_data(10000)
            model.train(data)

        # Test multiple scenarios
        for dist in [5, 15, 30]:
            for fin in [30, 60, 90]:
                xg = model.predict({
                    "distance_to_goal": dist, "angle": 30, "body_part": "foot",
                    "is_close_range": dist < 10, "preceding_action": "open_play",
                    "defender_proximity": 2, "game_state": "drawing",
                    "shooter_finishing": fin, "shooter_composure": 65,
                    "gk_quality": 65, "is_counter": False, "minute_bucket": 3,
                })
                assert 0 <= xg <= 1, f"xG {xg} out of range for dist={dist}, fin={fin}"

    def test_xg_calibration(self):
        """Mean predicted xG should be within 5% of actual conversion rate on test data."""
        from fm.engine.ml.xg_model import XGModel
        from fm.engine.ml.training_data import generate_shot_data

        np.random.seed(42)
        data = generate_shot_data(50000)
        model = XGModel()
        model.train(data.iloc[:40000])

        test = data.iloc[40000:]
        features = model.FEATURES
        preds = model.predict_batch(test[features])
        actual_rate = test["goal"].mean()
        pred_rate = preds.mean()

        assert abs(pred_rate - actual_rate) < 0.05, \
            f"Calibration off: predicted {pred_rate:.3f} vs actual {actual_rate:.3f}"


class TestMatchPredictor:
    """Match outcome predictor tests."""

    def test_home_advantage(self):
        """Equal teams should favor home side."""
        from fm.engine.ml.match_predictor import MatchPredictor
        from fm.engine.ml.training_data import generate_match_data

        np.random.seed(42)
        data = generate_match_data(20000)
        model = MatchPredictor()
        model.train(data)

        result = model.predict(
            home_overall=70, away_overall=70,
            home_form=7.5, away_form=7.5,
            home_adv=0.06, tactical=0.0,
            fatigue_diff=0, morale_diff=0,
        )
        assert result["home_win"] > result["away_win"], \
            f"Home win {result['home_win']:.3f} should > away win {result['away_win']:.3f}"

    def test_strong_team_favored(self):
        """Much stronger team should be heavily favored."""
        from fm.engine.ml.match_predictor import MatchPredictor
        from fm.engine.ml.training_data import generate_match_data

        np.random.seed(42)
        data = generate_match_data(20000)
        model = MatchPredictor()
        model.train(data)

        result = model.predict(
            home_overall=85, away_overall=55,
            home_form=12, away_form=3,
            home_adv=0.06, tactical=0.1,
            fatigue_diff=5, morale_diff=20,
        )
        assert result["home_win"] > 0.6, f"Strong home team should win > 60%, got {result['home_win']:.3f}"


class TestValuationModel:
    """Player valuation model tests."""

    def test_elite_worth_more_than_average(self):
        """Elite player should be valued higher than league two player."""
        from fm.engine.ml.valuation_model import ValuationModel
        from fm.engine.ml.training_data import generate_valuation_data

        np.random.seed(42)
        data = generate_valuation_data(10000)
        model = ValuationModel()
        model.train(data)

        elite = model.predict(age=26, overall=90, potential=92, position_group="FWD",
                             league_tier=1, minutes_pct=0.9, goals_per_90=0.8,
                             contract_years=4, form=85)
        average = model.predict(age=28, overall=62, potential=64, position_group="DEF",
                               league_tier=3, minutes_pct=0.7, goals_per_90=0.0,
                               contract_years=2, form=50)

        assert elite > average * 5, f"Elite {elite:.1f}M should be >> average {average:.1f}M"

    def test_valuation_positive(self):
        """All valuations should be positive."""
        from fm.engine.ml.valuation_model import ValuationModel
        from fm.engine.ml.training_data import generate_valuation_data

        np.random.seed(42)
        data = generate_valuation_data(5000)
        model = ValuationModel()
        model.train(data)

        val = model.predict(age=35, overall=55, potential=55, position_group="GK",
                           league_tier=4, minutes_pct=0.3, goals_per_90=0.0,
                           contract_years=1, form=40)
        assert val > 0, f"Valuation should be positive, got {val}"
