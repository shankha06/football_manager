"""Model persistence utilities."""

from __future__ import annotations

from pathlib import Path

import joblib

MODEL_DIR = Path("data/models")


def _ensure_dir() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


def save_model(model: object, name: str) -> Path:
    """Save a model to disk. Returns the path written."""
    _ensure_dir()
    path = MODEL_DIR / f"{name}.joblib"
    joblib.dump(model, path)
    return path


def load_model(name: str) -> object:
    """Load a model from disk."""
    path = MODEL_DIR / f"{name}.joblib"
    return joblib.load(path)


def model_exists(name: str) -> bool:
    """Check whether a saved model file exists."""
    return (MODEL_DIR / f"{name}.joblib").exists()


def train_all_models() -> None:
    """Generate data, train all three ML models, and save them."""
    from fm.engine.ml.match_predictor import MatchPredictor
    from fm.engine.ml.training_data import (
        generate_match_data,
        generate_shot_data,
        generate_valuation_data,
    )
    from fm.engine.ml.valuation_model import ValuationModel
    from fm.engine.ml.xg_model import XGModel

    print("Generating shot data...")
    shot_data = generate_shot_data()
    xg = XGModel()
    print("Training xG model...")
    xg.train(shot_data)
    xg.save()

    print("Generating match data...")
    match_data = generate_match_data()
    mp = MatchPredictor()
    print("Training match predictor...")
    mp.train(match_data)
    mp.save()

    print("Generating valuation data...")
    val_data = generate_valuation_data()
    vm = ValuationModel()
    print("Training valuation model...")
    vm.train(val_data)
    vm.save()

    print("All models trained and saved.")
