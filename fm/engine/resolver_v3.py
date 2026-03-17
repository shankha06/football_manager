"""V3 resolver — delegates shots to ML xG model when available.

All other resolution functions are re-exported from the base resolver
with identical signatures.  The key difference is ``resolve_shot_v3``
which uses the trained xG model to determine goal probability instead
of the formula-based approach.
"""
from __future__ import annotations

import random

from fm.engine.match_state import PlayerInMatch
from fm.engine.resolver import (
    ResolutionResult,
    resolve_cross,
    resolve_dribble,
    resolve_free_kick,
    resolve_header,
    resolve_interception,
    resolve_pass,
    resolve_penalty,
    resolve_shot as _resolve_shot_v2,
    resolve_tackle,
)
from fm.engine.tactics import TacticalContext
from fm.utils.helpers import clamp

# Re-export everything the chain engine needs
__all__ = [
    "ResolutionResult",
    "resolve_pass",
    "resolve_dribble",
    "resolve_shot_v3",
    "resolve_cross",
    "resolve_header",
    "resolve_tackle",
    "resolve_interception",
    "resolve_penalty",
    "resolve_free_kick",
]

# ---------------------------------------------------------------------------
# Try to load the ML xG model; fall back gracefully
# ---------------------------------------------------------------------------
_xg_model = None
_xg_available = False

try:
    from fm.engine.ml.xg_model import get_xg_model as _get_xg_model
    _xg_available = True
except ImportError:
    _xg_available = False


def _get_model():
    """Lazy-load the singleton xG model."""
    global _xg_model
    if _xg_model is None and _xg_available:
        try:
            _xg_model = _get_xg_model()
        except Exception:
            pass
    return _xg_model


# ---------------------------------------------------------------------------
# V3 shot resolver
# ---------------------------------------------------------------------------

def resolve_shot_v3(
    shooter: PlayerInMatch,
    gk: PlayerInMatch | None,
    nearest_defender: PlayerInMatch | None,
    zone_col: int,
    zone_row: int,
    tactics: TacticalContext,
    psychology_mods: dict | None = None,
    sabotage_penalty: float = 0.0,
) -> ResolutionResult:
    """Resolve a shot using the ML xG model when available.

    Falls back to the formula-based V2 resolver if sklearn / the
    trained model is not available.

    Args:
        shooter: The shooting player.
        gk: Opposing goalkeeper (may be None).
        nearest_defender: Closest defender.
        zone_col: Ball zone column (0-5).
        zone_row: Ball zone row (0-2).
        tactics: Possessing team's tactical context.
        psychology_mods: Optional dict from PsychologyEngine with keys
            like ``"composure_mod"``, ``"crowd_pressure"``.
        sabotage_penalty: Sabotage penalty (legacy, default 0).
    """
    model = _get_model()

    if model is None:
        # Fall back to V2 formula-based resolver
        return _resolve_shot_v2(
            shooter, gk, nearest_defender, zone_col, zone_row, tactics,
            sabotage_penalty=sabotage_penalty,
        )

    # --- Build feature dict for ML model ---
    is_close = zone_col >= 4 and zone_row == 1
    distance_to_goal = max(0.0, 5 - zone_col) * 10.0 + (0 if zone_row == 1 else 8.0)

    if zone_row == 1:
        angle = 0.0  # central
    elif zone_row == 0:
        angle = -30.0  # left
    else:
        angle = 30.0  # right

    gk_quality = 50.0
    if gk:
        gk_quality = (
            gk.effective("gk_reflexes") * 0.30
            + gk.effective("gk_diving") * 0.25
            + gk.effective("gk_positioning") * 0.25
            + gk.effective("gk_handling") * 0.20
        )

    defender_proximity = 0.5
    if nearest_defender:
        defender_proximity = clamp(
            (nearest_defender.effective("marking") * 0.4
             + nearest_defender.effective("positioning") * 0.4
             + nearest_defender.effective("reactions") * 0.2) / 99.0,
            0.1, 1.0,
        )

    # Psychology modifiers
    psych = psychology_mods or {}
    composure_adj = psych.get("composure_mod", 0.0)
    crowd = psych.get("crowd_pressure", 0.0)

    features = {
        "distance_to_goal": distance_to_goal,
        "angle": angle,
        "body_part": "foot",
        "is_close_range": is_close,
        "preceding_action": "open_play",
        "defender_proximity": defender_proximity,
        "game_state": "level",
        "shooter_finishing": (shooter.effective("finishing") + composure_adj * 99.0) / 99.0,
        "shooter_composure": (shooter.effective("composure") + (composure_adj + crowd) * 99.0) / 99.0,
        "gk_quality": gk_quality / 99.0,
        "is_counter": False,
        "minute_bucket": min(zone_col, 5),  # re-use as a generic numeric feature
    }

    # --- Get xG from model ---
    try:
        raw_xg = clamp(model.predict(features), 0.01, 0.75)
    except Exception:
        # If prediction fails, fall back
        return _resolve_shot_v2(
            shooter, gk, nearest_defender, zone_col, zone_row, tactics,
            sabotage_penalty=sabotage_penalty,
        )

    # --- Is this a big chance? ---
    is_big_chance = is_close and raw_xg > 0.25
    if is_big_chance:
        shooter.big_chances += 1

    # --- Blocked? ---
    block_chance = 0.0
    if nearest_defender:
        block_chance = clamp(
            (nearest_defender.effective("marking") * 0.3
             + nearest_defender.effective("positioning") * 0.3) / 99.0,
            0.05, 0.40,
        )

    if random.random() < block_chance * 0.6:
        shooter.shots += 1
        shooter.shots_blocked += 1
        shooter.rating_events += 1
        if nearest_defender:
            nearest_defender.blocks += 1
        return ResolutionResult(
            success=False, xg_value=raw_xg, detail="blocked", is_blocked=True,
        )

    # --- On target? ---
    if is_close:
        accuracy = clamp(
            shooter.effective("finishing") / 99.0 * 0.60 + composure_adj * 0.1,
            0.30, 0.60,
        )
    else:
        accuracy = clamp(
            shooter.effective("long_shots") / 99.0 * 0.35 + composure_adj * 0.05,
            0.08, 0.35,
        )

    on_target = random.random() < accuracy
    shooter.shots += 1

    if not on_target:
        if random.random() < 0.08:
            shooter.hit_woodwork += 1
            shooter.rating_events += 1
            return ResolutionResult(
                success=False, xg_value=raw_xg, detail="woodwork", hit_woodwork=True,
            )
        shooter.rating_events += 1
        if is_big_chance:
            shooter.big_chances_missed += 1
        return ResolutionResult(success=False, xg_value=raw_xg, detail="off_target")

    shooter.shots_on_target += 1

    # --- GK save attempt (modified by xG) ---
    if gk:
        # Higher xG → harder to save
        save_chance = clamp(
            gk_quality / 99.0 * (1.0 - raw_xg * 0.5) + 0.12 - crowd * 0.05,
            0.18, 0.74,
        )
        if random.random() < save_chance:
            gk.saves += 1
            gk.rating_points += 0.15
            gk.rating_events += 1
            shooter.rating_events += 1
            if is_big_chance:
                shooter.big_chances_missed += 1
            return ResolutionResult(success=False, xg_value=raw_xg, detail="saved")

    # --- GOAL! ---
    shooter.goals += 1
    shooter.rating_points += 0.5
    shooter.rating_events += 1
    return ResolutionResult(success=True, xg_value=raw_xg, detail="goal")
