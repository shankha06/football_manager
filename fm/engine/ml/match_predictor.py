"""Match outcome prediction model."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier

from fm.engine.ml.model_store import load_model, model_exists, save_model

FEATURES = [
    "home_overall",
    "away_overall",
    "home_form_points",
    "away_form_points",
    "home_advantage",
    "tactical_matchup",
    "fatigue_diff",
    "morale_diff",
]


class MatchPredictor:
    """Gradient-boosting classifier for match outcomes (home/draw/away)."""

    def __init__(self) -> None:
        self.model: GradientBoostingClassifier | None = None
        if model_exists("match_predictor"):
            self.load()

    def train(self, data: pd.DataFrame) -> None:
        """Train on match data with columns FEATURES + 'result'."""
        self.model = GradientBoostingClassifier(
            n_estimators=50, max_depth=4, random_state=42
        )
        self.model.fit(data[FEATURES], data["result"])

    def predict(
        self,
        home_overall: float,
        away_overall: float,
        home_form: float,
        away_form: float,
        home_adv: float,
        tactical: float,
        fatigue_diff: float,
        morale_diff: float,
    ) -> dict[str, float]:
        """Return probabilities for home_win, draw, away_win."""
        if self.model is None:
            self._auto_train()
        row = pd.DataFrame(
            [
                {
                    "home_overall": home_overall,
                    "away_overall": away_overall,
                    "home_form_points": home_form,
                    "away_form_points": away_form,
                    "home_advantage": home_adv,
                    "tactical_matchup": tactical,
                    "fatigue_diff": fatigue_diff,
                    "morale_diff": morale_diff,
                }
            ]
        )
        probs = self.model.predict_proba(row[FEATURES])[0]
        # Classes are 0=home_win, 1=draw, 2=away_win
        classes = list(self.model.classes_)
        result = {"home_win": 0.0, "draw": 0.0, "away_win": 0.0}
        label_map = {0: "home_win", 1: "draw", 2: "away_win"}
        for cls, prob in zip(classes, probs):
            result[label_map[int(cls)]] = float(prob)
        return result

    def save(self, path: str | None = None) -> None:
        if path is None:
            save_model(self.model, "match_predictor")
        else:
            import joblib
            joblib.dump(self.model, path)

    def load(self, path: str | None = None) -> None:
        if path is None:
            self.model = load_model("match_predictor")
        else:
            import joblib
            self.model = joblib.load(path)

    def _auto_train(self) -> None:
        from fm.engine.ml.training_data import generate_match_data

        data = generate_match_data()
        self.train(data)
        self.save()


_singleton: MatchPredictor | None = None


def get_match_predictor() -> MatchPredictor:
    """Return a singleton MatchPredictor, training on first use if needed."""
    global _singleton
    if _singleton is None:
        _singleton = MatchPredictor()
        if _singleton.model is None:
            _singleton._auto_train()
    return _singleton
