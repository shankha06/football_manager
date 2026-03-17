"""CUDA-accelerated batch match simulator for background matches.

Uses CuPy when a CUDA GPU is available, otherwise falls back to NumPy.
Simulates N matches in parallel by vectorising the core
possession / zone-control / shot-chance loop at the minute level.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from fm.config import get_array_module, USE_CUDA, MATCH_MINUTES

xp = get_array_module()


@dataclass
class BatchFixtureInput:
    """Minimal per-fixture data needed for batch sim."""
    fixture_id: int
    home_attack: float    # avg attacking attributes
    home_midfield: float  # avg midfield attributes
    home_defense: float   # avg defensive attributes
    home_gk: float        # GK rating
    away_attack: float
    away_midfield: float
    away_defense: float
    away_gk: float
    home_mentality: float = 0.0   # risk modifier
    away_mentality: float = 0.0
    # Context factors
    home_advantage: float = 0.06
    home_morale_mod: float = 0.0
    away_morale_mod: float = 0.0
    home_form_mod: float = 0.0
    away_form_mod: float = 0.0
    home_fitness: float = 1.0     # fatigue_home from MatchContext
    away_fitness: float = 1.0
    tactical_adv_home: float = 0.0
    tactical_adv_away: float = 0.0


@dataclass
class BatchMatchResult:
    """Output for one match from the batch simulator."""
    fixture_id: int
    home_goals: int = 0
    away_goals: int = 0
    home_possession: float = 50.0
    home_shots: int = 0
    away_shots: int = 0
    home_xg: float = 0.0
    away_xg: float = 0.0


class BatchMatchSimulator:
    """Simulate many matches at once using GPU-accelerated array operations.

    Operates at minute-level granularity (90 iterations) rather than
    tick-level (540) for dramatically faster CPU fallback performance.
    """

    def simulate_batch(self, fixtures: list[BatchFixtureInput]) -> list[BatchMatchResult]:
        """Simulate N matches in parallel."""
        N = len(fixtures)
        if N == 0:
            return []

        t0 = time.perf_counter()

        # ── Pack data into arrays ──────────────────────────────────────────
        h_att = xp.array([f.home_attack for f in fixtures], dtype=xp.float32)
        h_mid = xp.array([f.home_midfield for f in fixtures], dtype=xp.float32)
        h_def = xp.array([f.home_defense for f in fixtures], dtype=xp.float32)
        h_gk  = xp.array([f.home_gk for f in fixtures], dtype=xp.float32)
        a_att = xp.array([f.away_attack for f in fixtures], dtype=xp.float32)
        a_mid = xp.array([f.away_midfield for f in fixtures], dtype=xp.float32)
        a_def = xp.array([f.away_defense for f in fixtures], dtype=xp.float32)
        a_gk  = xp.array([f.away_gk for f in fixtures], dtype=xp.float32)
        h_risk = xp.array([f.home_mentality for f in fixtures], dtype=xp.float32)
        a_risk = xp.array([f.away_mentality for f in fixtures], dtype=xp.float32)

        # Context factor arrays
        home_adv = xp.array([f.home_advantage for f in fixtures], dtype=xp.float32)
        h_morale = xp.array([f.home_morale_mod for f in fixtures], dtype=xp.float32)
        a_morale = xp.array([f.away_morale_mod for f in fixtures], dtype=xp.float32)
        h_form = xp.array([f.home_form_mod for f in fixtures], dtype=xp.float32)
        a_form = xp.array([f.away_form_mod for f in fixtures], dtype=xp.float32)
        h_fitness = xp.array([f.home_fitness for f in fixtures], dtype=xp.float32)
        a_fitness = xp.array([f.away_fitness for f in fixtures], dtype=xp.float32)
        h_tac_adv = xp.array([f.tactical_adv_home for f in fixtures], dtype=xp.float32)
        a_tac_adv = xp.array([f.tactical_adv_away for f in fixtures], dtype=xp.float32)

        # Combined context modifier per side (clamped to -0.15 to +0.15)
        h_ctx = xp.clip(home_adv + h_morale + h_form + h_tac_adv, -0.15, 0.15)
        a_ctx = xp.clip(a_morale + a_form + a_tac_adv, -0.15, 0.15)

        # Derived strength ratios — context boosts both attack AND defense
        h_mid_eff = h_mid * (1.0 + h_ctx * 0.25) * h_fitness
        a_mid_eff = a_mid * (1.0 + a_ctx * 0.25) * a_fitness
        h_mid_ratio = h_mid_eff / (h_mid_eff + a_mid_eff + 1e-6)
        a_mid_ratio = 1.0 - h_mid_ratio

        h_att_eff = h_att * (1.0 + h_ctx * 0.35) * h_fitness
        a_def_eff = a_def * (1.0 + a_ctx * 0.20) * a_fitness
        a_att_eff = a_att * (1.0 + a_ctx * 0.35) * a_fitness
        h_def_eff = h_def * (1.0 + h_ctx * 0.20) * h_fitness

        h_att_ratio = h_att_eff / (h_att_eff + a_def_eff + a_gk * 0.4 + 1e-6)
        a_att_ratio = a_att_eff / (a_att_eff + h_def_eff + h_gk * 0.4 + 1e-6)

        # Soft-clamp extreme ratios (compress only the tails, preserve separation)
        h_att_ratio = xp.clip(h_att_ratio, 0.25, 0.65)
        a_att_ratio = xp.clip(a_att_ratio, 0.25, 0.65)

        # Shot probability per minute (tuned to ~11-13 shots/team/match)
        h_shot_prob = xp.clip(0.075 + h_att_ratio * 0.09 * (1.0 + h_risk * 0.20), 0.06, 0.16)
        a_shot_prob = xp.clip(0.075 + a_att_ratio * 0.09 * (1.0 + a_risk * 0.20), 0.06, 0.16)

        # Goal probability per shot (real football: ~10-11% of shots are goals)
        # Tighter ceiling prevents blowouts while rewarding quality
        h_goal_prob_per_shot = xp.clip(0.04 + h_att_ratio * 0.10, 0.05, 0.13)
        a_goal_prob_per_shot = xp.clip(0.04 + a_att_ratio * 0.10, 0.05, 0.13)

        # xG per shot (real football: ~0.10-0.12 avg xG per shot)
        h_xg_per_shot = xp.clip(0.05 + h_att_ratio * 0.08, 0.05, 0.14)
        a_xg_per_shot = xp.clip(0.05 + a_att_ratio * 0.08, 0.05, 0.14)

        # Accumulators
        h_goals = xp.zeros(N, dtype=xp.int32)
        a_goals = xp.zeros(N, dtype=xp.int32)
        h_poss = xp.zeros(N, dtype=xp.float32)
        h_shots_acc = xp.zeros(N, dtype=xp.int32)
        a_shots_acc = xp.zeros(N, dtype=xp.int32)
        h_xg = xp.zeros(N, dtype=xp.float32)
        a_xg = xp.zeros(N, dtype=xp.float32)

        # ── Simulation loop (per-minute) ───────────────────────────────────
        for minute in range(MATCH_MINUTES):
            # Possession this minute (home fraction)
            noise = xp.random.normal(0, 0.05, N).astype(xp.float32)
            poss_home = xp.clip(h_mid_ratio + noise, 0.25, 0.75)
            h_poss += poss_home

            # Home shots (more likely when home has possession)
            h_shot_roll = xp.random.random(N).astype(xp.float32)
            h_shot_mask = h_shot_roll < (h_shot_prob * (0.6 + poss_home * 0.8))
            h_shots_acc += h_shot_mask.astype(xp.int32)

            # Home goals from shots
            h_goal_roll = xp.random.random(N).astype(xp.float32)
            h_goal_mask = h_shot_mask & (h_goal_roll < h_goal_prob_per_shot)
            h_goals += h_goal_mask.astype(xp.int32)
            h_xg += h_xg_per_shot * h_shot_mask.astype(xp.float32)

            # Away shots
            a_shot_roll = xp.random.random(N).astype(xp.float32)
            poss_away = 1.0 - poss_home
            a_shot_mask = a_shot_roll < (a_shot_prob * (0.6 + poss_away * 0.8))
            a_shots_acc += a_shot_mask.astype(xp.int32)

            # Away goals from shots
            a_goal_roll = xp.random.random(N).astype(xp.float32)
            a_goal_mask = a_shot_mask & (a_goal_roll < a_goal_prob_per_shot)
            a_goals += a_goal_mask.astype(xp.int32)
            a_xg += a_xg_per_shot * a_shot_mask.astype(xp.float32)

        # ── Unpack results ─────────────────────────────────────────────────
        if USE_CUDA:
            h_goals_np = xp.asnumpy(h_goals)
            a_goals_np = xp.asnumpy(a_goals)
            h_poss_np = xp.asnumpy(h_poss)
            h_shots_np = xp.asnumpy(h_shots_acc)
            a_shots_np = xp.asnumpy(a_shots_acc)
            h_xg_np = xp.asnumpy(h_xg)
            a_xg_np = xp.asnumpy(a_xg)
        else:
            h_goals_np = h_goals
            a_goals_np = a_goals
            h_poss_np = h_poss
            h_shots_np = h_shots_acc
            a_shots_np = a_shots_acc
            h_xg_np = h_xg
            a_xg_np = a_xg

        results = []
        for i in range(N):
            h_poss_pct = (float(h_poss_np[i]) / MATCH_MINUTES) * 100.0
            # Cap extreme scorelines (real football rarely exceeds 6 goals for one team)
            hg = min(int(h_goals_np[i]), 6)
            ag = min(int(a_goals_np[i]), 6)
            results.append(BatchMatchResult(
                fixture_id=fixtures[i].fixture_id,
                home_goals=hg,
                away_goals=ag,
                home_possession=round(h_poss_pct, 1),
                home_shots=int(h_shots_np[i]),
                away_shots=int(a_shots_np[i]),
                home_xg=round(float(h_xg_np[i]), 2),
                away_xg=round(float(a_xg_np[i]), 2),
            ))

        elapsed = time.perf_counter() - t0
        backend = "CUDA/CuPy" if USE_CUDA else "CPU/NumPy"
        # For debugging: uncomment to see timing
        # print(f"[BatchSim] {N} matches in {elapsed:.3f}s ({backend})")

        return results
