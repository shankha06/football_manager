"""Player valuation model."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

from fm.engine.ml.model_store import load_model, model_exists, save_model

FEATURES = [
    "age",
    "overall",
    "potential",
    "position_group",
    "league_tier",
    "minutes_pct",
    "goals_per_90",
    "contract_years",
    "form",
]

CATEGORICAL = ["position_group"]


class ValuationModel:
    """Random-forest regressor for player market valuation (millions EUR)."""

    def __init__(self) -> None:
        self.model: RandomForestRegressor | None = None
        self.encoders: dict[str, LabelEncoder] = {}
        if model_exists("valuation_model"):
            self.load()

    def _encode(self, df: pd.DataFrame, *, fit: bool = False) -> pd.DataFrame:
        df = df.copy()
        for col in CATEGORICAL:
            if fit:
                le = LabelEncoder()
                df[col] = le.fit_transform(df[col].astype(str))
                self.encoders[col] = le
            else:
                le = self.encoders[col]
                mapping = {label: idx for idx, label in enumerate(le.classes_)}
                df[col] = df[col].astype(str).map(mapping).fillna(0).astype(int)
        return df

    def train(self, data: pd.DataFrame) -> None:
        """Train on valuation data with columns FEATURES + 'value_millions'."""
        encoded = self._encode(data[FEATURES], fit=True)
        # Train on log-values for better fit, predict will exponentiate
        self.model = RandomForestRegressor(
            n_estimators=100, max_depth=8, random_state=42, n_jobs=-1
        )
        self.model.fit(encoded, np.log1p(data["value_millions"]))

    def predict(
        self,
        age: int,
        overall: int,
        potential: int,
        position_group: str,
        league_tier: int,
        minutes_pct: float,
        goals_per_90: float,
        contract_years: float,
        form: float,
    ) -> float:
        """Return estimated market value in millions EUR."""
        if self.model is None:
            self._auto_train()
        row = pd.DataFrame(
            [
                {
                    "age": age,
                    "overall": overall,
                    "potential": potential,
                    "position_group": position_group,
                    "league_tier": league_tier,
                    "minutes_pct": minutes_pct,
                    "goals_per_90": goals_per_90,
                    "contract_years": contract_years,
                    "form": form,
                }
            ]
        )
        encoded = self._encode(row[FEATURES])
        log_pred = self.model.predict(encoded)[0]
        return float(np.expm1(log_pred))

    def save(self, path: str | None = None) -> None:
        bundle = {"model": self.model, "encoders": self.encoders}
        if path is None:
            save_model(bundle, "valuation_model")
        else:
            import joblib
            joblib.dump(bundle, path)

    def load(self, path: str | None = None) -> None:
        if path is None:
            bundle = load_model("valuation_model")
        else:
            import joblib
            bundle = joblib.load(path)
        self.model = bundle["model"]
        self.encoders = bundle["encoders"]

    def _auto_train(self) -> None:
        from fm.engine.ml.training_data import generate_valuation_data

        data = generate_valuation_data()
        self.train(data)
        self.save()


_singleton: ValuationModel | None = None


def get_valuation_model() -> ValuationModel:
    """Return a singleton ValuationModel, training on first use if needed."""
    global _singleton
    if _singleton is None:
        _singleton = ValuationModel()
        if _singleton.model is None:
            _singleton._auto_train()
    return _singleton
