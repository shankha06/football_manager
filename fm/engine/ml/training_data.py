"""Generate synthetic training data for ML models."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_shot_data(n_samples: int = 100_000) -> pd.DataFrame:
    """Generate synthetic shot data with realistic conversion probabilities."""
    rng = np.random.default_rng(42)

    distance = rng.uniform(3, 35, n_samples)
    angle = rng.uniform(0, 80, n_samples)
    body_part = rng.choice(["foot", "head", "volley"], n_samples, p=[0.70, 0.20, 0.10])
    is_close_range = distance < 10
    preceding_action = rng.choice(
        ["open_play", "counter", "set_piece", "cross", "through_ball"],
        n_samples,
        p=[0.40, 0.15, 0.15, 0.18, 0.12],
    )
    defender_proximity = rng.uniform(0, 5, n_samples)
    game_state = rng.choice(["winning", "drawing", "losing"], n_samples, p=[0.30, 0.40, 0.30])
    shooter_finishing = rng.integers(1, 100, n_samples)
    shooter_composure = rng.integers(1, 100, n_samples)
    gk_quality = rng.integers(1, 100, n_samples)
    is_counter = preceding_action == "counter"
    minute_bucket = rng.integers(0, 6, n_samples)

    # Build base conversion probability
    base_prob = np.full(n_samples, 0.10)

    # Distance effect: closer = higher
    base_prob += np.clip((20 - distance) / 40, -0.05, 0.20)

    # Angle effect: central = higher
    base_prob += np.clip((angle - 20) / 200, -0.02, 0.10)

    # Close range + central angle bonus
    close_central = is_close_range & (angle > 30)
    base_prob[close_central] += 0.15

    # Long range penalty
    long_range = distance > 25
    base_prob[long_range] -= 0.08

    # Body part adjustments
    base_prob[body_part == "head"] -= 0.04
    base_prob[body_part == "volley"] += 0.02

    # Preceding action adjustments
    base_prob[preceding_action == "counter"] += 0.03
    base_prob[preceding_action == "through_ball"] += 0.04
    base_prob[preceding_action == "cross"] -= 0.01

    # Defender proximity: further away = easier
    base_prob += np.clip((defender_proximity - 2) / 20, -0.03, 0.05)

    # Shooter quality
    base_prob += (shooter_finishing - 50) / 500
    base_prob += (shooter_composure - 50) / 800

    # Goalkeeper quality reduces probability
    base_prob -= (gk_quality - 50) / 500

    # Game state: losing slightly increases (desperation / higher risk taking)
    base_prob[game_state == "losing"] += 0.01

    # Clamp to valid range
    base_prob = np.clip(base_prob, 0.01, 0.65)

    goal = rng.random(n_samples) < base_prob

    return pd.DataFrame(
        {
            "distance_to_goal": distance,
            "angle": angle,
            "body_part": body_part,
            "is_close_range": is_close_range,
            "preceding_action": preceding_action,
            "defender_proximity": defender_proximity,
            "game_state": game_state,
            "shooter_finishing": shooter_finishing,
            "shooter_composure": shooter_composure,
            "gk_quality": gk_quality,
            "is_counter": is_counter,
            "minute_bucket": minute_bucket,
            "goal": goal.astype(int),
        }
    )


def generate_match_data(n_samples: int = 50_000) -> pd.DataFrame:
    """Generate synthetic match outcome data.

    Target distribution: ~45% home win, ~27% draw, ~28% away win.
    """
    rng = np.random.default_rng(123)

    home_overall = rng.integers(55, 90, n_samples).astype(float)
    away_overall = rng.integers(55, 90, n_samples).astype(float)
    home_form_points = rng.uniform(0, 15, n_samples)
    away_form_points = rng.uniform(0, 15, n_samples)
    home_advantage = rng.uniform(0.03, 0.08, n_samples)
    tactical_matchup = rng.uniform(-0.25, 0.25, n_samples)
    fatigue_diff = rng.uniform(-20, 20, n_samples)
    morale_diff = rng.uniform(-30, 30, n_samples)

    # Compute a strength differential that drives outcome probabilities
    overall_diff = (home_overall - away_overall) / 100.0
    form_diff = (home_form_points - away_form_points) / 30.0
    fatigue_effect = fatigue_diff / 200.0
    morale_effect = morale_diff / 300.0

    strength = (
        overall_diff * 1.5
        + form_diff * 0.3
        + home_advantage
        + tactical_matchup * 0.4
        + fatigue_effect
        + morale_effect
    )

    # Convert strength to outcome probabilities via softmax-style mapping
    home_logit = 0.5 + strength * 2.0
    draw_logit = np.full(n_samples, -0.1)
    away_logit = 0.5 - strength * 2.0

    logits = np.stack([home_logit, draw_logit, away_logit], axis=1)
    exp_logits = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

    result = np.array(
        [rng.choice([0, 1, 2], p=probs[i]) for i in range(n_samples)]
    )

    return pd.DataFrame(
        {
            "home_overall": home_overall,
            "away_overall": away_overall,
            "home_form_points": home_form_points,
            "away_form_points": away_form_points,
            "home_advantage": home_advantage,
            "tactical_matchup": tactical_matchup,
            "fatigue_diff": fatigue_diff,
            "morale_diff": morale_diff,
            "result": result,
        }
    )


def generate_valuation_data(n_samples: int = 30_000) -> pd.DataFrame:
    """Generate synthetic player valuation data with log-normal target."""
    rng = np.random.default_rng(456)

    age = rng.integers(16, 41, n_samples)
    overall = rng.integers(40, 100, n_samples)
    potential = np.clip(overall + rng.integers(-5, 20, n_samples), 40, 99)
    position_group = rng.choice(["GK", "DEF", "MID", "FWD"], n_samples, p=[0.10, 0.35, 0.30, 0.25])
    league_tier = rng.integers(1, 5, n_samples)
    minutes_pct = rng.uniform(0, 1, n_samples)
    goals_per_90 = rng.uniform(0, 2, n_samples)
    contract_years = rng.uniform(0, 5, n_samples)
    form = rng.uniform(0, 100, n_samples)

    # Reduce goals for non-attackers
    goals_per_90[position_group == "GK"] *= 0.01
    goals_per_90[position_group == "DEF"] *= 0.15
    goals_per_90[position_group == "MID"] *= 0.50

    # Build log-value from features
    log_value = np.full(n_samples, 0.0)

    # Overall is the primary driver
    log_value += (overall - 50) * 0.08

    # Potential premium for young players
    potential_gap = np.clip(potential - overall, 0, 30)
    youth_bonus = np.where(age < 24, potential_gap * 0.05, potential_gap * 0.01)
    log_value += youth_bonus

    # Age curve: peak at 25-29, drops sharply after 32
    age_factor = np.where(
        age < 23, -0.3 + (age - 16) * 0.05,
        np.where(age <= 29, 0.1, -0.05 * (age - 29))
    )
    log_value += age_factor

    # League tier: top league = premium
    log_value -= (league_tier - 1) * 0.25

    # Playing time and form
    log_value += minutes_pct * 0.3
    log_value += (form - 50) / 200

    # Goals premium for attackers
    log_value += goals_per_90 * 0.2

    # Contract: more years = higher value (club leverage)
    log_value += contract_years * 0.08

    # Position premium: FWD > MID > DEF > GK
    pos_premium = {"GK": -0.3, "DEF": 0.0, "MID": 0.1, "FWD": 0.2}
    for pos, prem in pos_premium.items():
        log_value[position_group == pos] += prem

    # Add noise and exponentiate
    noise = rng.normal(0, 0.3, n_samples)
    value_millions = np.exp(log_value + noise)
    value_millions = np.clip(value_millions, 0.01, 200)

    return pd.DataFrame(
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
            "value_millions": value_millions,
        }
    )
