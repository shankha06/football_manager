"""Expected goals (xG) prediction model."""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

from fm.engine.ml.model_store import MODEL_DIR, model_exists, load_model, save_model


class XGModel:
    """Logistic-regression xG model."""

    FEATURES = [
        "distance_to_goal",
        "angle",
        "body_part",
        "is_close_range",
        "preceding_action",
        "defender_proximity",
        "game_state",
        "shooter_finishing",
        "shooter_composure",
        "gk_quality",
        "is_counter",
        "minute_bucket",
    ]

    CATEGORICAL = ["body_part", "preceding_action", "game_state"]

    def __init__(self) -> None:
        self.model: LogisticRegression | None = None
        self.encoders: dict[str, LabelEncoder] = {}
        if model_exists("xg_model"):
            self.load()

    # ------------------------------------------------------------------
    def _encode(self, df: pd.DataFrame, *, fit: bool = False) -> pd.DataFrame:
        """Encode categorical columns to numeric."""
        df = df.copy()
        for col in self.CATEGORICAL:
            if fit:
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                self.encoders[col] = le
            else:
                le = self.encoders[col]
                # Handle unseen labels gracefully
                mapping = {label: idx for idx, label in enumerate(le.classes_)}
                df[col] = df[col].astype(str).map(mapping).fillna(0).astype(int)
        # Ensure bool columns are int
        for col in ["is_close_range", "is_counter"]:
            df[col] = df[col].astype(int)
        return df

    # ------------------------------------------------------------------
    def train(self, data: pd.DataFrame) -> None:
        """Train on shot data. *data* must contain FEATURES + 'goal'."""
        encoded = self._encode(data[self.FEATURES], fit=True)
        self.model = LogisticRegression(max_iter=500, solver="lbfgs")
        self.model.fit(encoded, data["goal"])

    def predict(self, features: Dict) -> float:
        """Return xG probability for a single shot."""
        if self.model is None:
            self._auto_train()
        row = pd.DataFrame([features])[self.FEATURES]
        encoded = self._encode(row)
        return float(self.model.predict_proba(encoded)[0, 1])

    def predict_batch(self, features_df: pd.DataFrame) -> np.ndarray:
        """Return xG probabilities for many shots."""
        if self.model is None:
            self._auto_train()
        encoded = self._encode(features_df[self.FEATURES])
        return self.model.predict_proba(encoded)[:, 1]

    # ------------------------------------------------------------------
    def save(self, path: str | None = None) -> None:
        if path is None:
            save_model({"model": self.model, "encoders": self.encoders}, "xg_model")
        else:
            import joblib
            joblib.dump({"model": self.model, "encoders": self.encoders}, path)

    def load(self, path: str | None = None) -> None:
        if path is None:
            bundle = load_model("xg_model")
        else:
            import joblib
            bundle = joblib.load(path)
        self.model = bundle["model"]
        self.encoders = bundle["encoders"]

    # ------------------------------------------------------------------
    def _auto_train(self) -> None:
        from fm.engine.ml.training_data import generate_shot_data

        data = generate_shot_data()
        self.train(data)
        self.save()


# ------------------------------------------------------------------
_singleton: XGModel | None = None


def get_xg_model() -> XGModel:
    """Return a singleton XGModel, training on first use if needed."""
    global _singleton
    if _singleton is None:
        _singleton = XGModel()
        if _singleton.model is None:
            _singleton._auto_train()
    return _singleton
