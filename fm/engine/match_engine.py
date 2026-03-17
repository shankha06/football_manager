"""Advanced V2 Match Engine — possession-chain simulation.

Replaces the tick-by-tick random-event model with a realistic possession-chain
system where each period of possession is a sequence of deliberate actions
(pass, dribble, through ball, cross, shot, etc.) that build up play logically.

Drop-in replacement for MatchSimulator: same ``simulate()`` signature,
same ``MatchResult`` output, fully compatible with UI / DB / stats layers.
"""
from __future__ import annotations

import enum
import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from fm.core.match_situations import MatchSituationEngine

from fm.config import (
    MATCH_MINUTES, SCORECARD_INTERVAL,
    FATIGUE_PER_MINUTE, FATIGUE_SPRINT_COST, INJURY_BASE_CHANCE,
)
from fm.engine.match_state import (
    PlayerInMatch, MatchState, MatchResult, Scorecard,
)
from fm.engine.pitch import Pitch, ZoneCol, ZoneRow, N_COLS, N_ROWS
from fm.engine.tactics import TacticalContext, FORMATIONS
from fm.engine.resolver import (
    resolve_pass, resolve_dribble, resolve_shot, resolve_cross,
    resolve_header, resolve_tackle, resolve_interception,
    resolve_penalty, resolve_free_kick,
    ResolutionResult,
)
from fm.engine.commentary import Commentary
from fm.engine.roles import get_role_biases, get_role_offset
from fm.utils.helpers import clamp, weighted_random_choice, zone_distance


# ═══════════════════════════════════════════════════════════════════════════
#  Data Structures
# ═══════════════════════════════════════════════════════════════════════════

class MatchPhase(enum.Enum):
    """Current tactical phase of play."""
    BUILDUP = "buildup"
    TRANSITION = "transition"
    ESTABLISHED_ATTACK = "attack"
    FINAL_THIRD = "final_third"
    SET_PIECE = "set_piece"
    COUNTER = "counter"
    PRESSING = "pressing"


class SetPieceType(enum.Enum):
    CORNER = "corner"
    FREE_KICK_DIRECT = "free_kick_direct"
    FREE_KICK_CROSS = "free_kick_cross"
    FREE_KICK_SHORT = "free_kick_short"
    THROW_IN = "throw_in"
    GOAL_KICK_SHORT = "goal_kick_short"
    GOAL_KICK_LONG = "goal_kick_long"
    PENALTY = "penalty"


class CornerRoutine(enum.Enum):
    NEAR_POST = "near_post"
    FAR_POST = "far_post"
    SHORT = "short"
    TRAINING_GROUND = "training_ground"


class PenaltyStyle(enum.Enum):
    POWER = "power"
    PLACEMENT = "placement"
    STUTTER = "stutter"


@dataclass
class Action:
    """A single action within a possession chain."""
    action_type: str  # pass, dribble, shot, cross, through_ball, etc.
    player: PlayerInMatch
    target: Optional[PlayerInMatch] = None
    zone_from: tuple[int, int] = (3, 1)
    zone_to: tuple[int, int] = (3, 1)
    success: bool = False
    result: Optional[ResolutionResult] = None


@dataclass
class PossessionPhase:
    """Tracks a continuous period of possession by one team."""
    side: str
    start_minute: int
    actions: list[Action] = field(default_factory=list)
    zones_visited: list[tuple[int, int]] = field(default_factory=list)
    players_involved: list[int] = field(default_factory=list)
    outcome: str = "turnover"  # shot, turnover, foul, set_piece, out_of_play
    phase: MatchPhase = MatchPhase.BUILDUP


# ═══════════════════════════════════════════════════════════════════════════
#  Partnership Tracker
# ═══════════════════════════════════════════════════════════════════════════

class PartnershipTracker:
    """Track real-time passing connections and in-match chemistry."""

    def __init__(self):
        self._passes: dict[tuple[int, int], int] = {}
        self._successes: dict[tuple[int, int], int] = {}

    def record_pass(self, from_id: int, to_id: int, success: bool) -> None:
        key = (from_id, to_id)
        self._passes[key] = self._passes.get(key, 0) + 1
        if success:
            self._successes[key] = self._successes.get(key, 0) + 1

    def get_chemistry(self, p1_id: int, p2_id: int) -> float:
        """Return 0.0-1.0 how well two players have connected this match."""
        key = (p1_id, p2_id)
        rev = (p2_id, p1_id)
        total = self._passes.get(key, 0) + self._passes.get(rev, 0)
        good = self._successes.get(key, 0) + self._successes.get(rev, 0)
        if total == 0:
            return 0.0
        # Chemistry grows with volume and accuracy
        accuracy = good / total
        volume_bonus = min(total / 20.0, 0.3)
        return clamp(accuracy * 0.7 + volume_bonus, 0.0, 1.0)

    def get_preferred_partner(self, player_id: int,
                              candidates: list[PlayerInMatch]) -> Optional[PlayerInMatch]:
        """Return the candidate with the best existing chemistry."""
        if not candidates:
            return None
        best = None
        best_chem = -1.0
        for c in candidates:
            chem = self.get_chemistry(player_id, c.player_id)
            if chem > best_chem:
                best_chem = chem
                best = c
        return best if best_chem > 0.0 else None

    def get_pass_network(self) -> dict[tuple[int, int], int]:
        return dict(self._successes)


# ═══════════════════════════════════════════════════════════════════════════
#  xG Model (Enhanced)
# ═══════════════════════════════════════════════════════════════════════════

class XGModel:
    """Calculate expected goals based on football-analytics principles."""

    # Zone columns mapped to approximate distance from goal (meters)
    _COL_DISTANCE = {
        ZoneCol.FINAL_THIRD: 8.0,
        ZoneCol.ATTACK: 20.0,
        ZoneCol.MIDFIELD: 32.0,
        ZoneCol.DEEP_MID: 42.0,
        ZoneCol.DEFENSE: 55.0,
        ZoneCol.GK_AREA: 70.0,
    }

    @classmethod
    def calculate(
        cls,
        zone_col: int,
        zone_row: int,
        body_part: str = "foot",
        assist_type: str = "open_play",
        is_counter: bool = False,
        defenders_in_path: int = 2,
        gk_off_line: bool = False,
        is_set_piece: bool = False,
    ) -> float:
        """Return xG value in [0.01, 0.95]."""
        distance = cls._COL_DISTANCE.get(zone_col, 35.0)

        # Base xG from distance (exponential decay)
        # Calibrated to produce ~0.10-0.12 avg xG/shot (real football)
        # 8m (6-yard box): ~0.30, 20m (edge of box): ~0.08, 32m: ~0.03
        base_xg = math.exp(-0.10 * distance) * 0.65

        # Angle factor: central = full, wings = reduced
        if zone_row == ZoneRow.CENTER:
            angle_factor = 1.0
        else:
            angle_factor = 0.55 if zone_col >= ZoneCol.ATTACK else 0.40

        base_xg *= angle_factor

        # Body part modifier
        body_mod = {"foot": 1.0, "head": 0.70, "volley": 0.55, "other": 0.45}
        base_xg *= body_mod.get(body_part, 1.0)

        # Assist type
        assist_mod = {
            "through_ball": 1.30,
            "cross": 0.75,
            "cutback": 1.15,
            "set_piece": 0.85,
            "corner": 0.60,
            "open_play": 1.0,
            "counter": 1.25,
            "one_two": 1.20,
            "rebound": 1.10,
        }
        base_xg *= assist_mod.get(assist_type, 1.0)

        # Defenders in path (each defender reduces xG)
        def_factor = max(0.3, 1.0 - defenders_in_path * 0.12)
        base_xg *= def_factor

        # Counter attacks have fewer defenders set
        if is_counter:
            base_xg *= 1.15

        # GK off their line = higher xG on lobs/chips
        if gk_off_line:
            base_xg *= 1.20

        return clamp(base_xg, 0.01, 0.80)


# ═══════════════════════════════════════════════════════════════════════════
#  Match Rating Calculator
# ═══════════════════════════════════════════════════════════════════════════

class MatchRatingCalculator:
    """Calculate realistic player match ratings on a 1-10 scale.

    Target distribution (like real football):
      - 5.0-5.9: Poor performance (~15%)
      - 6.0-6.9: Average/decent (~45%)
      - 7.0-7.9: Good performance (~25%)
      - 8.0-8.9: Excellent (~12%)
      - 9.0-10.0: World-class display (~3%)
    """

    @staticmethod
    def calculate(p: PlayerInMatch) -> float:
        rating = 6.0

        # ── Attacking contributions ──────────────────────────────────
        # Goals are the biggest single-event boost
        rating += min(p.goals * 1.2, 3.0)

        # Assists
        rating += min(p.assists * 0.7, 1.5)

        # Key passes (creative contribution)
        rating += min(p.key_passes * 0.15, 0.6)

        # Shots on target (threatening the goal)
        rating += min(p.shots_on_target * 0.12, 0.5)

        # Big chances missed (penalty for wastefulness)
        rating -= min(p.big_chances_missed * 0.25, 0.5)

        # ── Passing & build-up ───────────────────────────────────────
        if p.passes_attempted >= 10:
            acc = p.passes_completed / p.passes_attempted
            if acc >= 0.92:
                rating += 0.40
            elif acc >= 0.87:
                rating += 0.25
            elif acc >= 0.80:
                rating += 0.10
            elif acc < 0.65:
                rating -= 0.20

        # ── Dribbling & ball-carrying ────────────────────────────────
        rating += min(p.dribbles_completed * 0.12, 0.5)
        # Failed dribbles penalised
        failed_dribbles = p.dribbles_attempted - p.dribbles_completed
        rating -= min(failed_dribbles * 0.06, 0.3)

        # ── Defensive work ───────────────────────────────────────────
        rating += min(p.tackles_won * 0.12, 0.6)
        rating += min(p.interceptions_made * 0.12, 0.6)
        rating += min(p.clearances * 0.08, 0.4)
        rating += min(p.blocks * 0.10, 0.3)

        # Failed tackles (rash challenges)
        failed_tackles = p.tackles_attempted - p.tackles_won
        rating -= min(failed_tackles * 0.05, 0.2)

        # ── Aerial duels ────────────────────────────────────────────
        rating += min(p.aerials_won * 0.08, 0.3)

        # ── Fouls & discipline ──────────────────────────────────────
        rating -= p.yellow_cards * 0.30
        rating -= (1.5 if p.red_card else 0.0)
        rating -= min(p.fouls_committed * 0.04, 0.3)
        # Drawing fouls is positive (winning free kicks)
        rating += min(p.fouls_won * 0.05, 0.2)

        # ── Crossing accuracy ───────────────────────────────────────
        if p.crosses_attempted >= 3:
            cross_acc = p.crosses_completed / p.crosses_attempted
            if cross_acc >= 0.40:
                rating += 0.15
            elif cross_acc < 0.15:
                rating -= 0.10

        # ── GK-specific ─────────────────────────────────────────────
        if p.is_gk:
            rating += min(p.saves * 0.20, 1.0)
            # Penalty for goals conceded relative to saves
            # (clean sheet bonus applied externally in _finalize_ratings)

        # ── Position-based involvement bonus ─────────────────────────
        # Reward players who were actively involved in the match
        # Midfielders need involvement, defenders need defensive actions
        if not p.is_gk:
            involvement = (
                p.passes_completed + p.tackles_won + p.interceptions_made
                + p.dribbles_completed + p.key_passes + p.shots
                + p.clearances + p.blocks + p.aerials_won
            )
            if involvement >= 40:
                rating += 0.30   # Very active player
            elif involvement >= 25:
                rating += 0.15   # Active
            elif involvement < 8:
                rating -= 0.15   # Ghost performance

        # Clamp to realistic range
        return clamp(rating, 3.0, 10.0)


# ═══════════════════════════════════════════════════════════════════════════
#  Player Decision Engine
# ═══════════════════════════════════════════════════════════════════════════

class PlayerDecisionEngine:
    """Determines what each player does when they receive the ball.

    Decisions are based on position, zone, attributes, tactics, match state,
    momentum, form, defensive pressure, and available teammates.
    """

    # Action weights per zone column (attacking direction: 0=own GK, 5=opponent box)
    # Values are base weights for: pass, dribble, shot, cross, through_ball,
    # switch_play, hold_up, lay_off, long_ball, one_two, run_in_behind
    #
    # BALANCE: Real football — even in the final third most actions are passes,
    # crosses, or turnovers, NOT shots.  Only ~10-15 shots per team per match.
    _ZONE_ACTION_WEIGHTS = {
        0: {"pass": 55, "long_ball": 25, "goal_kick": 20},
        1: {"pass": 55, "dribble": 8, "long_ball": 15, "switch_play": 15,
            "play_out": 10},
        2: {"pass": 45, "dribble": 10, "long_ball": 10, "switch_play": 15,
            "through_ball": 6, "lay_off": 5, "one_two": 5, "hold_up": 4},
        3: {"pass": 30, "dribble": 12, "through_ball": 10, "switch_play": 10,
            "one_two": 8, "shot": 6, "lay_off": 8, "long_ball": 5,
            "run_in_behind": 8, "cross": 3},
        4: {"pass": 20, "dribble": 10, "shot": 14, "cross": 18,
            "through_ball": 10, "one_two": 8, "lay_off": 8,
            "run_in_behind": 10},
        5: {"shot": 25, "cross": 18, "dribble": 6, "pass": 12,
            "lay_off": 12, "one_two": 8, "through_ball": 5, "hold_up": 5},
    }

    def decide_action(
        self,
        carrier: PlayerInMatch,
        state: MatchState,
        tactics: TacticalContext,
        match_context: Optional[object],
        phase: MatchPhase,
        defenders_nearby: int,
    ) -> str:
        """Choose what the ball carrier does next."""
        # Get the zone column from attacking perspective
        col = carrier.zone_col
        if carrier.side == "away":
            col = N_COLS - 1 - col

        weights = dict(self._ZONE_ACTION_WEIGHTS.get(col, self._ZONE_ACTION_WEIGHTS[3]))

        # Remove goal_kick unless it is a GK
        if "goal_kick" in weights and not carrier.is_gk:
            del weights["goal_kick"]
        if "play_out" in weights and not carrier.position in ("GK", "CB"):
            del weights["play_out"]

        # --- Attribute biases (kept small to avoid inflating shot counts) ---
        if carrier.effective("dribbling") > 75:
            weights["dribble"] = weights.get("dribble", 0) + 4
        if carrier.effective("vision") > 75:
            weights["through_ball"] = weights.get("through_ball", 0) + 3
            weights["switch_play"] = weights.get("switch_play", 0) + 2
        if carrier.effective("long_passing") > 75:
            weights["long_ball"] = weights.get("long_ball", 0) + 3
            weights["switch_play"] = weights.get("switch_play", 0) + 2
        if carrier.effective("finishing") > 75 and col >= 4:
            weights["shot"] = weights.get("shot", 0) + 3
        if carrier.effective("crossing") > 75 and carrier.zone_row != ZoneRow.CENTER:
            weights["cross"] = weights.get("cross", 0) + 4
        if carrier.effective("strength") > 75:
            weights["hold_up"] = weights.get("hold_up", 0) + 3
        if carrier.effective("short_passing") > 80:
            weights["one_two"] = weights.get("one_two", 0) + 3

        # --- Tactical modifiers ---
        # Direct / possession style
        if tactics.passing_style in ("direct", "very_direct"):
            weights["long_ball"] = weights.get("long_ball", 0) + 10
            weights["through_ball"] = weights.get("through_ball", 0) + 5
            weights["pass"] = max(weights.get("pass", 0) - 8, 2)
        elif tactics.passing_style in ("short", "very_short"):
            weights["pass"] = weights.get("pass", 0) + 10
            weights["lay_off"] = weights.get("lay_off", 0) + 5
            weights["long_ball"] = max(weights.get("long_ball", 0) - 8, 0)

        # Attacking mentality = more risk (but modest effect)
        risk = tactics.risk_modifier
        if risk > 0.1:
            weights["shot"] = weights.get("shot", 0) + 2
            weights["through_ball"] = weights.get("through_ball", 0) + 3
            weights["dribble"] = weights.get("dribble", 0) + 2
        elif risk < -0.1:
            weights["pass"] = weights.get("pass", 0) + 5
            weights["long_ball"] = weights.get("long_ball", 0) + 2
            weights["shot"] = max(weights.get("shot", 0) - 3, 0)

        # Width affects crossing
        if tactics.width in ("wide", "very_wide"):
            weights["cross"] = weights.get("cross", 0) + 6
            weights["switch_play"] = weights.get("switch_play", 0) + 4

        # --- Match state modifiers ---
        side = carrier.side
        own_goals = state.home_goals if side == "home" else state.away_goals
        opp_goals = state.away_goals if side == "home" else state.home_goals
        goal_diff = own_goals - opp_goals
        minute = state.current_minute

        # Losing late = more risk (but capped to stay realistic)
        if goal_diff < 0 and minute > 70:
            urgency = min(abs(goal_diff) * 2, 6)
            weights["shot"] = weights.get("shot", 0) + urgency
            weights["cross"] = weights.get("cross", 0) + urgency
            weights["through_ball"] = weights.get("through_ball", 0) + urgency
        # Winning comfortably = keep ball
        elif goal_diff >= 2 and minute > 60:
            weights["pass"] = weights.get("pass", 0) + 12
            weights["lay_off"] = weights.get("lay_off", 0) + 5
            weights["shot"] = max(weights.get("shot", 0) - 5, 0)

        # --- Phase modifiers ---
        if phase == MatchPhase.COUNTER:
            weights["through_ball"] = weights.get("through_ball", 0) + 6
            weights["long_ball"] = weights.get("long_ball", 0) + 4
            weights["run_in_behind"] = weights.get("run_in_behind", 0) + 4
            weights["pass"] = max(weights.get("pass", 0) - 3, 2)
        elif phase == MatchPhase.PRESSING:
            weights["pass"] = weights.get("pass", 0) + 5  # safe pass under pressure
        elif phase == MatchPhase.BUILDUP:
            weights["pass"] = weights.get("pass", 0) + 6
            weights["play_out"] = weights.get("play_out", 0) + 3

        # --- Defensive pressure ---
        if defenders_nearby >= 3:
            weights["pass"] = weights.get("pass", 0) + 8
            weights["lay_off"] = weights.get("lay_off", 0) + 4
            weights["dribble"] = max(weights.get("dribble", 0) - 6, 0)
        elif defenders_nearby == 0:
            weights["dribble"] = weights.get("dribble", 0) + 3
            if col >= 5:  # only in the box, not just "attack" zone
                weights["shot"] = weights.get("shot", 0) + 4

        # --- Tiredness ---
        if carrier.stamina_current < 40:
            weights["pass"] = weights.get("pass", 0) + 10
            weights["lay_off"] = weights.get("lay_off", 0) + 5
            weights["dribble"] = max(weights.get("dribble", 0) - 8, 0)
            weights["run_in_behind"] = max(weights.get("run_in_behind", 0) - 8, 0)

        # --- Momentum ---
        momentum = state.get_momentum(side)
        if momentum > 0.3:
            weights["shot"] = weights.get("shot", 0) + 2
            weights["through_ball"] = weights.get("through_ball", 0) + 2

        # --- Tactical matchup effects on action selection ---
        if match_context and hasattr(match_context, "tactical_matchup") and match_context.tactical_matchup:
            tm = match_context.tactical_matchup.for_side(side)

            # Width exploitation: encourages crosses and wide play
            if tm["width"] > 0.05:
                bonus = int(tm["width"] * 30)  # up to ~7
                weights["cross"] = weights.get("cross", 0) + bonus
                weights["switch_play"] = weights.get("switch_play", 0) + bonus // 2

            # Counter advantage: more through balls and runs in behind
            if tm["counter"] > 0.05 and phase == MatchPhase.COUNTER:
                bonus = int(tm["counter"] * 25)  # up to ~6
                weights["through_ball"] = weights.get("through_ball", 0) + bonus
                weights["run_in_behind"] = weights.get("run_in_behind", 0) + bonus

            # Creative advantage: better at unlocking defences
            if tm["creative"] > 0.05:
                bonus = int(tm["creative"] * 20)
                weights["through_ball"] = weights.get("through_ball", 0) + bonus
                weights["one_two"] = weights.get("one_two", 0) + bonus

            # Midfield control: more patient build-up, keep ball better
            if tm["midfield"] > 0.05:
                bonus = int(tm["midfield"] * 20)
                weights["pass"] = weights.get("pass", 0) + bonus
                weights["lay_off"] = weights.get("lay_off", 0) + bonus // 2

            # Opponent's defensive solidity: harder to find openings
            if tm["defensive"] < -0.05:  # opponent is solid against us
                penalty = int(abs(tm["defensive"]) * 20)
                weights["shot"] = max(weights.get("shot", 0) - penalty, 3)  # never zero
                weights["through_ball"] = max(weights.get("through_ball", 0) - penalty // 2, 2)
                weights["pass"] = weights.get("pass", 0) + penalty // 2  # some recycling

            # Aerial advantage: more crosses and long balls
            if tm["aerial"] > 0.05:
                bonus = int(tm["aerial"] * 20)
                weights["cross"] = weights.get("cross", 0) + bonus
                weights["long_ball"] = weights.get("long_ball", 0) + bonus // 2

        # --- Role-specific action biases ---
        role_biases = get_role_biases(carrier.role)
        for action, bias in role_biases.items():
            if action in weights:
                weights[action] = max(1, weights[action] + bias)

        # Remove zero-weight entries and choose
        weights = {k: max(v, 0) for k, v in weights.items() if v > 0}
        if not weights:
            return "pass"

        actions = list(weights.keys())
        w = list(weights.values())
        return weighted_random_choice(actions, w)


# ═══════════════════════════════════════════════════════════════════════════
#  Match Tactical Manager
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TacticalChange:
    """A mid-match tactical adjustment."""
    side: str
    change_type: str  # mentality, pressing, formation, tempo
    old_value: str
    new_value: str
    reason: str


class MatchTacticalManager:
    """AI adjusts tactics mid-match based on game state."""

    _MENTALITY_ORDER = [
        "very_defensive", "defensive", "cautious", "balanced",
        "positive", "attacking", "very_attacking",
    ]

    def evaluate_tactical_change(
        self, state: MatchState, minute: int,
        h_tac: TacticalContext, a_tac: TacticalContext,
    ) -> Optional[TacticalChange]:
        """Check if either AI side should adjust tactics."""
        if minute < 20 or minute % 5 != 0:
            return None

        for side, tac in [("home", h_tac), ("away", a_tac)]:
            own_goals = state.home_goals if side == "home" else state.away_goals
            opp_goals = state.away_goals if side == "home" else state.home_goals
            diff = own_goals - opp_goals

            idx = self._mentality_index(tac.mentality)

            # Losing after 60 — push forward
            if diff < 0 and minute >= 60 and idx < 5:
                new_idx = min(idx + 1, 6)
                new_ment = self._MENTALITY_ORDER[new_idx]
                if new_ment != tac.mentality:
                    old = tac.mentality
                    tac.mentality = new_ment
                    return TacticalChange(
                        side=side, change_type="mentality",
                        old_value=old, new_value=new_ment,
                        reason=f"Pushing forward while trailing at {minute}'",
                    )

            # Winning by 2+ after 70 — drop deeper
            if diff >= 2 and minute >= 70 and idx > 2:
                new_idx = max(idx - 1, 0)
                new_ment = self._MENTALITY_ORDER[new_idx]
                if new_ment != tac.mentality:
                    old = tac.mentality
                    tac.mentality = new_ment
                    return TacticalChange(
                        side=side, change_type="mentality",
                        old_value=old, new_value=new_ment,
                        reason=f"Protecting lead at {minute}'",
                    )

            # Dominating possession but not scoring — go more direct
            poss = state.home_possession_pct if side == "home" else 100.0 - state.home_possession_pct
            shots = state.home_shots if side == "home" else state.away_shots
            if poss > 60 and own_goals == 0 and minute >= 55 and shots < 5:
                if tac.passing_style in ("short", "very_short"):
                    old = tac.passing_style
                    tac.passing_style = "mixed"
                    return TacticalChange(
                        side=side, change_type="passing_style",
                        old_value=old, new_value="mixed",
                        reason="Too much sterile possession, mixing it up",
                    )

        return None

    def _mentality_index(self, mentality: str) -> int:
        try:
            return self._MENTALITY_ORDER.index(mentality)
        except ValueError:
            return 3


# ═══════════════════════════════════════════════════════════════════════════
#  Set Piece Engine
# ═══════════════════════════════════════════════════════════════════════════

class SetPieceEngine:
    """Detailed set piece resolution."""

    @staticmethod
    def resolve_corner(
        attacking: list[PlayerInMatch],
        defending: list[PlayerInMatch],
        att_tactics: TacticalContext,
        def_tactics: TacticalContext,
        gk: Optional[PlayerInMatch],
    ) -> tuple[str, Optional[ResolutionResult], Optional[PlayerInMatch], Optional[PlayerInMatch]]:
        """Resolve a corner kick.

        Returns (outcome, result, scorer_or_none, assister_or_none).
        Outcome is one of: 'goal', 'saved', 'cleared', 'off_target', 'short_won'.
        """
        # Pick taker (best crossing)
        taker = max(attacking, key=lambda p: p.effective("crossing") + p.effective("curve"))

        # Choose routine
        routine = random.choices(
            list(CornerRoutine),
            weights=[30, 30, 20, 20],
            k=1,
        )[0]

        if routine == CornerRoutine.SHORT:
            # Short corner — pass to nearby player, reset play
            return "short_won", None, None, taker

        # Identify aerial threats and markers
        targets = [p for p in attacking if p != taker and not p.is_gk]
        if not targets:
            return "cleared", None, None, None

        # Sort by heading threat
        targets.sort(
            key=lambda p: p.effective("heading_accuracy") + p.effective("jumping"),
            reverse=True,
        )
        target = targets[0] if routine == CornerRoutine.NEAR_POST else (
            targets[1] if len(targets) > 1 else targets[0]
        )

        # Defender assignment
        markers = [p for p in defending if not p.is_gk]
        marker = max(markers, key=lambda p: (
            p.effective("heading_accuracy") + p.effective("jumping")
            + p.effective("marking")
        )) if markers else None

        # Cross delivery quality
        cross_result = resolve_cross(taker, target, marker, att_tactics)
        if not cross_result.success:
            if marker:
                marker.clearances += 1
            return "cleared", cross_result, None, None

        # Header attempt
        header_result = resolve_header(target, gk, marker, att_tactics)
        assister = taker if header_result.success else None
        if assister:
            assister.assists += 1
            assister.key_passes += 1
            assister.rating_points += 0.3
            assister.rating_events += 1

        outcome = "goal" if header_result.success else header_result.detail
        scorer = target if header_result.success else None
        return outcome, header_result, scorer, assister

    @staticmethod
    def resolve_free_kick_situation(
        attacking: list[PlayerInMatch],
        defending: list[PlayerInMatch],
        att_tactics: TacticalContext,
        gk: Optional[PlayerInMatch],
        zone_col: int,
    ) -> tuple[str, Optional[ResolutionResult], Optional[PlayerInMatch], Optional[PlayerInMatch]]:
        """Resolve a free kick in a dangerous area.

        Decides between direct shot, cross, or short based on distance.
        """
        taker = max(attacking, key=lambda p: (
            p.effective("free_kick_accuracy") + p.effective("curve")
        ))

        # Distance from goal determines options
        att_col = zone_col  # already in attacking perspective
        is_shooting_range = att_col >= 4
        markers = [p for p in defending if not p.is_gk]
        wall = markers[0] if markers else None

        if is_shooting_range and random.random() < 0.55:
            # Direct free kick shot
            distance = max(0.5, (N_COLS - att_col) * 0.8)
            fk_result = resolve_free_kick(taker, gk, wall, distance, att_tactics)
            outcome = "goal" if fk_result.success else fk_result.detail
            scorer = taker if fk_result.success else None
            return outcome, fk_result, scorer, None
        else:
            # Crossed free kick — similar to corner
            targets = [p for p in attacking if p != taker and not p.is_gk]
            if not targets:
                return "cleared", None, None, None
            target = max(targets, key=lambda p: (
                p.effective("heading_accuracy") + p.effective("jumping")
            ))
            marker = max(markers, key=lambda p: (
                p.effective("heading_accuracy") + p.effective("marking")
            )) if markers else None

            cross_result = resolve_cross(taker, target, marker, att_tactics)
            if not cross_result.success:
                return "cleared", cross_result, None, None

            header_result = resolve_header(target, gk, marker, att_tactics)
            assister = taker if header_result.success else None
            if assister:
                assister.assists += 1
                assister.key_passes += 1
            outcome = "goal" if header_result.success else header_result.detail
            scorer = target if header_result.success else None
            return outcome, header_result, scorer, assister

    @staticmethod
    def resolve_penalty_kick(
        attacking: list[PlayerInMatch],
        gk: Optional[PlayerInMatch],
        tactics: TacticalContext,
    ) -> tuple[str, ResolutionResult, Optional[PlayerInMatch]]:
        """Resolve a penalty kick with style variation."""
        # Best penalty taker
        taker = max(attacking, key=lambda p: (
            p.effective("penalties") * 0.5 + p.effective("composure") * 0.3
            + p.effective("finishing") * 0.2
        ))

        # Choose style based on attributes
        if taker.effective("shot_power") > taker.effective("finishing"):
            _style = PenaltyStyle.POWER
        elif taker.effective("composure") > 80:
            _style = random.choice([PenaltyStyle.STUTTER, PenaltyStyle.PLACEMENT])
        else:
            _style = PenaltyStyle.PLACEMENT

        pen_result = resolve_penalty(taker, gk, tactics)
        outcome = "goal" if pen_result.success else pen_result.detail
        scorer = taker if pen_result.success else None
        return outcome, pen_result, scorer

    @staticmethod
    def resolve_throw_in(
        attacking: list[PlayerInMatch],
        zone_col: int,
        zone_row: int,
    ) -> tuple[PlayerInMatch, PlayerInMatch]:
        """Return (thrower, receiver) for a throw-in."""
        # Nearest outfield player throws
        candidates = [p for p in attacking if not p.is_gk and p.is_on_pitch]
        if not candidates:
            return attacking[0], attacking[0]
        # Pick thrower closest to the zone
        thrower = min(candidates, key=lambda p: abs(p.zone_col - zone_col) + abs(p.zone_row - zone_row))
        receivers = [p for p in candidates if p != thrower]
        if not receivers:
            return thrower, thrower
        receiver = min(receivers, key=lambda p: abs(p.zone_col - zone_col) + abs(p.zone_row - zone_row))
        return thrower, receiver

    @staticmethod
    def resolve_goal_kick(
        gk: Optional[PlayerInMatch],
        defenders: list[PlayerInMatch],
        attackers_opp: list[PlayerInMatch],
        tactics: TacticalContext,
    ) -> tuple[str, Optional[PlayerInMatch]]:
        """Resolve goal kick distribution. Returns (style, receiver)."""
        if gk is None:
            return "long", None

        # Short build-up if possession-oriented
        short_chance = 0.3
        if tactics.passing_style in ("short", "very_short"):
            short_chance = 0.55
        elif tactics.passing_style in ("direct", "very_direct"):
            short_chance = 0.10

        if random.random() < short_chance:
            # Short to defender
            cbs = [p for p in defenders if p.position in ("CB", "LB", "RB") and not p.is_gk]
            if cbs:
                receiver = random.choice(cbs)
                return "short", receiver
        return "long", None


# ═══════════════════════════════════════════════════════════════════════════
#  Advanced Match Engine
# ═══════════════════════════════════════════════════════════════════════════

class AdvancedMatchEngine:
    """V2 Match Engine with possession chains, spatial awareness,
    intelligent player decisions, and realistic set pieces.

    Drop-in replacement for MatchSimulator — same ``simulate()`` interface
    and ``MatchResult`` output.
    """

    # Maximum actions in a single possession chain (prevent infinite loops)
    MAX_CHAIN_LENGTH = 12

    # Average number of possession chains per minute
    # Real football ~200-250 possessions in 90 min ≈ 2.5/min
    CHAINS_PER_MINUTE = 2.6

    # Probability that a chain is just "dead" possession recycling (no shot)
    DEAD_POSSESSION_CHANCE = 0.20

    def __init__(self):
        self.pitch = Pitch()
        self.commentary = Commentary()
        self.decision_engine = PlayerDecisionEngine()
        self.partnership_tracker = PartnershipTracker()
        self.tactical_manager = MatchTacticalManager()
        self.rating_calculator = MatchRatingCalculator()
        self.xg_model = XGModel()
        self.set_piece_engine = SetPieceEngine()
        self._match_context: Optional[object] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def simulate(
        self,
        home_players: list[PlayerInMatch],
        away_players: list[PlayerInMatch],
        home_tactics: TacticalContext,
        away_tactics: TacticalContext,
        home_name: str = "Home",
        away_name: str = "Away",
        home_subs: list[PlayerInMatch] | None = None,
        away_subs: list[PlayerInMatch] | None = None,
        match_context=None,
    ) -> MatchResult:
        """Run the full 90-minute simulation.

        Interface matches MatchSimulator.simulate() for drop-in replacement.
        """
        self._match_context = match_context
        self.partnership_tracker = PartnershipTracker()

        # Apply context modifiers to all players
        if match_context is not None:
            self._apply_match_context(home_players, away_players, match_context)

        state = MatchState(
            home_players=home_players,
            away_players=away_players,
            home_subs=home_subs or [],
            away_subs=away_subs or [],
        )

        # Initial kickoff
        state.ball_side = random.choice(["home", "away"])
        state.ball_zone_col = 3
        state.ball_zone_row = 1

        # Kickoff commentary
        if match_context is not None:
            for line in match_context.kickoff_commentary():
                state.commentary.append(line)

        state.commentary.append(
            f"0' {home_name} vs {away_name} — kick off!"
        )

        # Make mutable copies of tactics so match plans can modify them
        h_tac_live = TacticalContext(
            formation=home_tactics.formation, mentality=home_tactics.mentality,
            tempo=home_tactics.tempo, pressing=home_tactics.pressing,
            passing_style=home_tactics.passing_style, width=home_tactics.width,
            defensive_line=home_tactics.defensive_line,
            offside_trap=home_tactics.offside_trap,
            counter_attack=home_tactics.counter_attack,
            play_out_from_back=home_tactics.play_out_from_back,
            time_wasting=home_tactics.time_wasting,
            match_plan_winning=home_tactics.match_plan_winning,
            match_plan_losing=home_tactics.match_plan_losing,
            match_plan_drawing=home_tactics.match_plan_drawing,
            roles=list(home_tactics.roles),
        )
        a_tac_live = TacticalContext(
            formation=away_tactics.formation, mentality=away_tactics.mentality,
            tempo=away_tactics.tempo, pressing=away_tactics.pressing,
            passing_style=away_tactics.passing_style, width=away_tactics.width,
            defensive_line=away_tactics.defensive_line,
            offside_trap=away_tactics.offside_trap,
            counter_attack=away_tactics.counter_attack,
            play_out_from_back=away_tactics.play_out_from_back,
            time_wasting=away_tactics.time_wasting,
            match_plan_winning=away_tactics.match_plan_winning,
            match_plan_losing=away_tactics.match_plan_losing,
            match_plan_drawing=away_tactics.match_plan_drawing,
            roles=list(away_tactics.roles),
        )

        # Assign roles to players
        outfield_h = [p for p in state.home_players if not p.is_gk]
        for i, p in enumerate(outfield_h):
            if i < len(h_tac_live.roles):
                p.role = h_tac_live.roles[i]
        
        outfield_a = [p for p in state.away_players if not p.is_gk]
        for i, p in enumerate(outfield_a):
            if i < len(a_tac_live.roles):
                p.role = a_tac_live.roles[i]

        # ── Main loop: 90 minutes ──
        for minute in range(1, MATCH_MINUTES + 1):
            state.current_minute = minute

            # Apply match plans at key moments (60', 75')
            if minute in (60, 75):
                self._apply_match_plans(
                    state, h_tac_live, a_tac_live, minute,
                    home_name, away_name,
                )

            self._simulate_minute(
                state, minute, h_tac_live, a_tac_live, home_name, away_name,
            )

            # Half-time
            if minute == 45:
                state.commentary.append(
                    f"45' -- HALF TIME -- "
                    f"{home_name} {state.home_goals}-{state.away_goals} "
                    f"{away_name}"
                )
                state.home_momentum *= 0.4
                state.away_momentum *= 0.4

            # Scorecard every N minutes
            if minute % SCORECARD_INTERVAL == 0:
                sc = self._generate_scorecard(state, minute)
                state.scorecards.append(sc)

        # ── Stoppage time ──
        extra = random.randint(1, 5)
        state.commentary.append(f"90' +{extra} minutes of added time.")
        for et in range(1, extra + 1):
            state.current_minute = 90 + et
            self._simulate_minute(
                state, 90 + et, h_tac_live, a_tac_live, home_name, away_name,
            )

        # ── Final whistle ──
        state.commentary.append(
            f"90+{extra}' -- FULL TIME -- "
            f"{home_name} {state.home_goals}-{state.away_goals} {away_name}"
        )

        # Calculate final ratings
        self._finalize_ratings(state)

        # Match Situations: Post-match analysis
        if state.home_goals == 0:
            gk = state.get_gk("home")
            if gk: self._trigger_situation(state, "handle_clean_sheet", player_id=gk.player_id)
        if state.away_goals == 0:
            gk = state.get_gk("away")
            if gk: self._trigger_situation(state, "handle_clean_sheet", player_id=gk.player_id)

        # comebacks / upsets
        if state.home_goals > state.away_goals:
            win_side = "home"
        elif state.away_goals > state.home_goals:
            win_side = "away"
        else:
            win_side = None

        if win_side:
            # Check for comeback / upset
            score_diff = abs(state.home_goals - state.away_goals)
            if score_diff >= 3:
                # Potential upset if ratings were lower? 
                # MatchSituationEngine usually handles reputation comparison.
                pass

        # Scoring runs
        for p in state.home_players + state.away_players:
            if p.goals > 0:
                self._trigger_situation(state, "handle_scoring_run", player_id=p.player_id)

        self._match_context = None
        return state.to_result()

    # ── Match plan adjustments ─────────────────────────────────────────────

    def _apply_match_plans(
        self,
        state: MatchState,
        h_tac: TacticalContext,
        a_tac: TacticalContext,
        minute: int,
        h_name: str,
        a_name: str,
    ) -> None:
        """Apply in-match tactical adjustments based on match plans.

        Match plans modify live tactics based on the current score state.
        This is how teams automatically react to being ahead/behind/level.
        """
        score_diff_h = state.home_goals - state.away_goals

        # Home team adjustments
        self._apply_plan_for_side(
            h_tac, score_diff_h, minute, h_name, state,
        )
        # Away team adjustments
        self._apply_plan_for_side(
            a_tac, -score_diff_h, minute, a_name, state,
        )

    def _apply_plan_for_side(
        self,
        tac: TacticalContext,
        score_diff: int,
        minute: int,
        team_name: str,
        state: MatchState,
    ) -> None:
        """Apply a single side's match plan based on score state."""
        if score_diff > 0:
            plan = tac.match_plan_winning
            if plan == "hold_lead":
                if minute >= 75:
                    tac.mentality = "cautious"
                    tac.tempo = "slow"
                else:
                    tac.mentality = "balanced"
            elif plan == "push_for_more":
                tac.mentality = "positive"
            elif plan == "time_waste":
                tac.mentality = "defensive"
                tac.tempo = "very_slow"
                if minute >= 80:
                    state.commentary.append(
                        f"{minute}' {team_name} are wasting time now..."
                    )
            elif plan == "park_the_bus":
                tac.mentality = "very_defensive"
                tac.pressing = "low"
                tac.defensive_line = "deep"
                tac.width = "narrow"

        elif score_diff < 0:
            plan = tac.match_plan_losing
            if plan == "push_forward":
                if minute >= 75:
                    tac.mentality = "attacking"
                else:
                    tac.mentality = "positive"
            elif plan == "all_out_attack":
                tac.mentality = "very_attacking"
                tac.pressing = "very_high"
                tac.width = "wide"
                if minute >= 80:
                    state.commentary.append(
                        f"{minute}' {team_name} are throwing everyone forward!"
                    )
            elif plan == "stay_calm":
                tac.mentality = "balanced"
            elif plan == "long_balls":
                tac.passing_style = "very_direct"
                tac.mentality = "attacking"

        else:  # drawing
            plan = tac.match_plan_drawing
            if plan == "push_forward":
                if minute >= 70:
                    tac.mentality = "positive"
            elif plan == "stay_balanced":
                pass  # no change
            elif plan == "tighten_up":
                tac.mentality = "cautious"
                tac.pressing = "standard"

    # ── Minute simulation ─────────────────────────────────────────────────

    def _simulate_minute(
        self,
        state: MatchState,
        minute: int,
        h_tac: TacticalContext,
        a_tac: TacticalContext,
        h_name: str,
        a_name: str,
    ) -> None:
        """Simulate one minute of play."""
        # Reposition players
        self._assign_zones(state, h_tac, a_tac)
        self._refresh_pitch(state)

        # Determine how many possession chains this minute
        # Real football: ~200-250 possessions per 90 min ≈ 2.2-2.8/min
        # Tempo/press add only minor variation, not doubling
        tempo_mod = abs(h_tac.tempo_modifier) + abs(a_tac.tempo_modifier)
        press_mod = abs(h_tac.press_modifier) + abs(a_tac.press_modifier)
        raw_chains = self.CHAINS_PER_MINUTE + tempo_mod * 0.3 + press_mod * 0.2 + random.uniform(-0.5, 0.5)
        chains = max(1, min(4, int(raw_chains)))  # hard cap at 4

        for _ in range(chains):
            # Some possessions are just uneventful recycling — no shot threat
            if random.random() < self.DEAD_POSSESSION_CHANCE:
                # Dead possession: ball recycled, record possession ticks but
                # no meaningful action (backwards passes, sideways play, etc.)
                dead_side = state.ball_side
                ticks = random.randint(1, 3)
                n_passes = random.randint(2, 5)
                n_completed = random.randint(max(1, n_passes - 1), n_passes)
                if dead_side == "home":
                    state.home_possession_ticks += ticks
                    state._inc("home", "passes", n_passes)
                    state._inc("home", "passes_completed", n_completed)
                else:
                    state.away_possession_ticks += ticks
                    state._inc("away", "passes", n_passes)
                    state._inc("away", "passes_completed", n_completed)
                # Occasionally change possession on dead ball
                if random.random() < 0.3:
                    self._change_possession(state)
                continue

            phase = self._determine_phase(state)
            possession = self._execute_possession_chain(
                state, h_tac, a_tac, h_name, a_name, phase,
            )

            # Record possession ticks (weight by chain length)
            ticks = max(1, len(possession.actions))
            if possession.side == "home":
                state.home_possession_ticks += ticks
            else:
                state.away_possession_ticks += ticks

        # Apply fatigue
        self._apply_fatigue(state, minute, h_tac, a_tac)

        # Injury check
        self._check_injuries(state, minute, h_name, a_name)

        # AI substitutions
        if minute >= 55:
            self._auto_subs(state, minute, h_name, a_name)

        # Dynamic tactical adjustments
        change = self.tactical_manager.evaluate_tactical_change(
            state, minute, h_tac, a_tac,
        )
        if change:
            name = h_name if change.side == "home" else a_name
            state.commentary.append(
                f"{minute}' {name} tactical change: {change.reason}"
            )

        # Momentum decay
        state._decay_momentum()

    # ── Phase determination ───────────────────────────────────────────────

    def _determine_phase(self, state: MatchState) -> MatchPhase:
        """Determine the current match phase based on ball position and context."""
        col = state.ball_zone_col
        side = state.ball_side

        # Attacking direction: home attacks towards col 5, away towards col 0
        att_col = col if side == "home" else (N_COLS - 1 - col)

        # Did possession just change? (Simple heuristic: check momentum)
        momentum = state.get_momentum(state.ball_side)
        opp_momentum = state.get_momentum("away" if state.ball_side == "home" else "home")

        # Counter: just won the ball + opponent was attacking
        counter_threshold = -0.1
        # Tactical matchup: counter advantage lowers the threshold (easier to trigger)
        if self._match_context and self._match_context.tactical_matchup:
            counter_adv = self._match_context.tactical_matchup.for_side(side)["counter"]
            counter_threshold -= counter_adv * 0.15  # up to ~0.04 easier/harder
        if opp_momentum < counter_threshold and momentum > 0.05:
            return MatchPhase.COUNTER

        if att_col <= 1:
            return MatchPhase.BUILDUP
        elif att_col == 2:
            return MatchPhase.TRANSITION if random.random() < 0.4 else MatchPhase.BUILDUP
        elif att_col == 3:
            return MatchPhase.ESTABLISHED_ATTACK
        elif att_col == 4:
            return MatchPhase.ESTABLISHED_ATTACK if random.random() < 0.5 else MatchPhase.FINAL_THIRD
        else:
            return MatchPhase.FINAL_THIRD

    # ── Possession Chain Execution ────────────────────────────────────────

    def _execute_possession_chain(
        self,
        state: MatchState,
        h_tac: TacticalContext,
        a_tac: TacticalContext,
        h_name: str,
        a_name: str,
        phase: MatchPhase,
    ) -> PossessionPhase:
        """Execute one possession sequence until it ends in a shot,
        turnover, foul, or out of play."""
        side = state.ball_side
        att_tactics = h_tac if side == "home" else a_tac
        def_tactics = a_tac if side == "home" else h_tac
        att_name = h_name if side == "home" else a_name
        def_name = a_name if side == "home" else h_name
        minute = state.current_minute

        possession = PossessionPhase(side=side, start_minute=minute, phase=phase)

        attackers = state.get_attacking_players()
        defenders = state.get_defending_players()
        if not attackers:
            possession.outcome = "turnover"
            return possession

        # Ensure valid carrier
        carrier = state.ball_carrier
        if carrier is None or not carrier.is_on_pitch or carrier.red_card or carrier.side != side:
            carrier = self._pick_initial_carrier(attackers, phase, state)
            state.ball_carrier = carrier

        for step in range(self.MAX_CHAIN_LENGTH):
            # Track zone visits
            zone = (carrier.zone_col, carrier.zone_row)
            possession.zones_visited.append(zone)
            if carrier.player_id not in possession.players_involved:
                possession.players_involved.append(carrier.player_id)

            # Count nearby defenders
            defenders_nearby = self._count_defenders_nearby(carrier, defenders)

            # --- Defensive pressure check ---
            # The deeper into the opponent's half, the harder it is to keep
            # the ball.  This models congestion, defensive shape, and the
            # natural tendency for possessions to break down before a shot.
            att_col = carrier.zone_col if side == "home" else (N_COLS - 1 - carrier.zone_col)
            # Base turnover probability scales with depth into opponent half
            depth_turnover = {0: 0.01, 1: 0.01, 2: 0.02, 3: 0.04, 4: 0.06, 5: 0.09}
            turnover_chance = depth_turnover.get(att_col, 0.03)
            # More defenders nearby = higher chance of losing it
            turnover_chance += defenders_nearby * 0.015
            # Pressing opponents increase pressure
            turnover_chance += max(0, def_tactics.press_modifier) * 0.03
            # Carrier composure / ball control resists turnovers
            resist = (carrier.effective("composure") + carrier.effective("ball_control")) / 200.0
            turnover_chance *= (1.0 - resist * 0.5)  # up to 50% reduction
            # Later chain steps are harder to sustain
            turnover_chance += step * 0.01

            # --- Tactical matchup effects on turnovers ---
            if self._match_context and self._match_context.tactical_matchup:
                tm = self._match_context.tactical_matchup.for_side(side)
                # Pressing advantage: opponent's press is more/less effective
                # Negative pressing value means opponent presses us better
                turnover_chance -= tm["pressing"] * 0.15
                # Midfield control: dominant midfield retains ball better
                turnover_chance -= tm["midfield"] * 0.10
                # Defensive solidity of OPPONENT makes it harder to progress
                turnover_chance += tm["defensive"] * 0.08  # opponent's def hurts us
                # Counter situations: if we're vulnerable to counters, turnovers
                # in our half become more dangerous (handled in counter trigger below)

            if random.random() < turnover_chance:
                possession.outcome = "turnover"
                state._update_momentum(side, "turnover")
                self._change_possession(state)
                break

            # Decide action
            action_type = self.decision_engine.decide_action(
                carrier, state, att_tactics, self._match_context, phase, defenders_nearby,
            )

            # Resolve action
            action, chain_over, new_carrier = self._resolve_chain_action(
                action_type, carrier, state, attackers, defenders,
                att_tactics, def_tactics, att_name, def_name, phase,
            )
            possession.actions.append(action)

            if chain_over:
                possession.outcome = self._classify_outcome(action)
                break

            # Continue chain with new carrier
            if new_carrier and new_carrier.is_on_pitch:
                carrier = new_carrier
                state.ball_carrier = carrier
            else:
                # Lost the ball
                possession.outcome = "turnover"
                self._change_possession(state)
                break

            # Update phase as ball progresses
            phase = self._determine_phase(state)
            possession.phase = phase
        else:
            # Chain maxed out — possession fizzles
            possession.outcome = "out_of_play"
            self._change_possession(state)

        return possession

    def _resolve_chain_action(
        self,
        action_type: str,
        carrier: PlayerInMatch,
        state: MatchState,
        attackers: list[PlayerInMatch],
        defenders: list[PlayerInMatch],
        att_tactics: TacticalContext,
        def_tactics: TacticalContext,
        att_name: str,
        def_name: str,
        phase: MatchPhase,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Resolve a single action in the possession chain.

        Returns (action, chain_ends, new_carrier_or_none).
        """
        minute = state.current_minute
        side = carrier.side
        nearest_def = self._nearest_defender(carrier, defenders)
        gk = state.get_gk("away" if side == "home" else "home")

        action = Action(
            action_type=action_type,
            player=carrier,
            zone_from=(carrier.zone_col, carrier.zone_row),
        )

        # ── PASS ──────────────────────────────────────────────────────
        if action_type == "pass":
            return self._do_chain_pass(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
                is_long=False,
            )

        # ── LONG BALL ─────────────────────────────────────────────────
        if action_type == "long_ball":
            return self._do_chain_pass(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
                is_long=True,
            )

        # ── THROUGH BALL ──────────────────────────────────────────────
        if action_type == "through_ball":
            return self._do_chain_through_ball(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute, gk,
            )

        # ── SWITCH PLAY ───────────────────────────────────────────────
        if action_type == "switch_play":
            return self._do_chain_switch_play(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
            )

        # ── DRIBBLE ───────────────────────────────────────────────────
        if action_type == "dribble":
            return self._do_chain_dribble(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
            )

        # ── SHOT ──────────────────────────────────────────────────────
        if action_type == "shot":
            return self._do_chain_shot(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute, gk,
                assist_type="open_play",
            )

        # ── CROSS ─────────────────────────────────────────────────────
        if action_type == "cross":
            return self._do_chain_cross(
                action, carrier, state, attackers, defenders,
                att_tactics, def_tactics, att_name, def_name, minute, gk,
            )

        # ── ONE-TWO ───────────────────────────────────────────────────
        if action_type == "one_two":
            return self._do_chain_one_two(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
            )

        # ── HOLD UP ───────────────────────────────────────────────────
        if action_type == "hold_up":
            return self._do_chain_hold_up(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, att_name, def_name, minute,
            )

        # ── LAY OFF ───────────────────────────────────────────────────
        if action_type == "lay_off":
            return self._do_chain_lay_off(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
            )

        # ── RUN IN BEHIND ─────────────────────────────────────────────
        if action_type == "run_in_behind":
            return self._do_chain_through_ball(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute, gk,
            )

        # ── PLAY OUT FROM BACK ────────────────────────────────────────
        if action_type in ("play_out", "goal_kick"):
            return self._do_chain_play_out(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
            )

        # Fallback: treat as pass
        return self._do_chain_pass(
            action, carrier, state, attackers, defenders, nearest_def,
            att_tactics, def_tactics, att_name, def_name, minute,
            is_long=False,
        )

    # ── Chain action implementations ──────────────────────────────────────

    def _do_chain_pass(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute,
        is_long=False,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Standard pass (short or long)."""
        # Pick target
        if is_long:
            # Target a forward player
            targets = [p for p in attackers if p != carrier and p.is_on_pitch and not p.is_gk]
            targets.sort(key=lambda p: p.zone_col if carrier.side == "home" else -p.zone_col, reverse=True)
            target = targets[0] if targets else None
        else:
            # Prefer chemistry partner, else nearby teammate
            target = self.partnership_tracker.get_preferred_partner(
                carrier.player_id,
                [p for p in attackers if p != carrier and p.is_on_pitch],
            )
            if target is None:
                candidates = [p for p in attackers if p != carrier and p.is_on_pitch]
                if candidates:
                    # Nearest teammate
                    candidates.sort(key=lambda p: zone_distance(
                        (carrier.zone_col, carrier.zone_row), (p.zone_col, p.zone_row)
                    ))
                    # Weight towards forward passes
                    fwd_bonus = []
                    for c in candidates[:5]:
                        dist = zone_distance((carrier.zone_col, carrier.zone_row), (c.zone_col, c.zone_row))
                        fwd = 1.0
                        if carrier.side == "home" and c.zone_col > carrier.zone_col:
                            fwd = 1.5
                        elif carrier.side == "away" and c.zone_col < carrier.zone_col:
                            fwd = 1.5
                        fwd_bonus.append(fwd / max(dist, 0.5))
                    pool = candidates[:5] if len(candidates) >= 5 else candidates
                    if fwd_bonus:
                        target = weighted_random_choice(pool, fwd_bonus)
                    else:
                        target = random.choice(candidates)

        if target is None:
            action.success = False
            return action, False, None

        action.target = target
        action.zone_to = (target.zone_col, target.zone_row)
        dist = zone_distance(action.zone_from, action.zone_to)
        if is_long:
            dist = max(dist, 3.0)

        # Check for interception first
        interceptor = self._find_interceptor(carrier, target, defenders, dist)
        if interceptor:
            int_result = resolve_interception(interceptor, carrier, dist)
            if int_result.success:
                self.partnership_tracker.record_pass(carrier.player_id, target.player_id, False)
                state._inc(carrier.side, "passes")
                carrier.passes_attempted += 1
                state._update_momentum(carrier.side, "turnover")
                self._change_possession(state)
                state.ball_carrier = interceptor
                state._inc(interceptor.side, "interceptions")
                action.success = False
                return action, True, None

        # Resolve pass
        sab_pen = self._match_context.performance_sabotage_penalty(carrier.side) if self._match_context else 0.0
        pass_result = resolve_pass(carrier, target, nearest_def, dist, att_tactics, sabotage_penalty=sab_pen)
        action.success = pass_result.success
        action.result = pass_result

        state._inc(carrier.side, "passes")
        if pass_result.success:
            state._inc(carrier.side, "passes_completed")
        self.partnership_tracker.record_pass(carrier.player_id, target.player_id, pass_result.success)

        if not pass_result.success:
            # Turnover
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            return action, True, None

        # Advance ball position
        state.ball_zone_col = target.zone_col
        state.ball_zone_row = target.zone_row
        return action, False, target

    def _do_chain_through_ball(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute, gk,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Through ball behind the defence. High risk/reward."""
        action.action_type = "through_ball"

        # Target: fastest forward player
        forwards = [p for p in attackers if p != carrier and not p.is_gk and p.is_on_pitch]
        if not forwards:
            action.success = False
            return action, False, None

        # Sort by pace + positioning (off-the-ball movement)
        forwards.sort(
            key=lambda p: p.effective("pace") * 0.5 + p.effective("positioning") * 0.3 + p.effective("acceleration") * 0.2,
            reverse=True,
        )
        target = forwards[0]
        action.target = target

        # Through ball success depends heavily on vision + passing
        vision = carrier.effective("vision")
        passing = carrier.effective("passing")
        composure = carrier.effective("composure")

        # Defender reading the play
        def_reading = 0.0
        if nearest_def:
            def_reading = (
                nearest_def.effective("positioning") * 0.4
                + nearest_def.effective("reactions") * 0.3
                + nearest_def.effective("interceptions") * 0.3
            )

        # Runner's movement quality
        runner_quality = (
            target.effective("positioning") * 0.3
            + target.effective("pace") * 0.3
            + target.effective("acceleration") * 0.2
            + target.effective("reactions") * 0.2
        )

        base_chance = (
            vision * 0.30 + passing * 0.25 + composure * 0.15 + runner_quality * 0.30
            - def_reading * 0.40
        ) / 99.0

        # Tactical bonus for direct play
        if att_tactics.passing_style in ("direct", "very_direct"):
            base_chance += 0.05

        # Offside check — high defensive line = more offside risk
        offside_risk = 0.12
        if def_tactics.defensive_line == "high":
            offside_risk = 0.22
        elif def_tactics.defensive_line == "deep":
            offside_risk = 0.06

        if random.random() < offside_risk:
            # Offside!
            state._inc(carrier.side, "offsides")
            target.offsides_count += 1
            action.success = False
            state.commentary.append(
                f"{minute}' {target.name} flagged offside from {carrier.name}'s through ball."
            )
            self._change_possession(state)
            return action, True, None

        success_chance = clamp(base_chance, 0.10, 0.55)
        carrier.passes_attempted += 1
        state._inc(carrier.side, "passes")

        if random.random() < success_chance:
            # Successful through ball — creates 1v1 or close-range chance
            carrier.passes_completed += 1
            carrier.key_passes += 1
            state._inc(carrier.side, "passes_completed")
            state._inc(carrier.side, "key_passes")
            carrier.rating_points += 0.15
            carrier.rating_events += 1
            self.partnership_tracker.record_pass(carrier.player_id, target.player_id, True)
            action.success = True

            state.commentary.append(
                f"{minute}' Brilliant through ball from {carrier.name} finds {target.name} in behind!"
            )

            # Move ball to final third / box
            if carrier.side == "home":
                state.ball_zone_col = min(N_COLS - 1, carrier.zone_col + 2)
            else:
                state.ball_zone_col = max(0, carrier.zone_col - 2)
            state.ball_zone_row = ZoneRow.CENTER

            # Immediate 1v1 shot with enhanced xG
            target.big_chances += 1
            defenders_in_path = random.randint(0, 1)
            xg_val = self.xg_model.calculate(
                zone_col=ZoneCol.FINAL_THIRD, zone_row=ZoneRow.CENTER,
                body_part="foot", assist_type="through_ball",
                is_counter=(state.get_momentum(carrier.side) > 0.15),
                defenders_in_path=defenders_in_path,
            )
            # Find nearest recovering defender (through-ball doesn't mean completely free)
            recovering_def = min(
                [d for d in defenders if d.is_on_pitch and not d.is_gk],
                key=lambda d: zone_distance(
                    (d.zone_col, d.zone_row),
                    (target.zone_col, target.zone_row),
                ),
                default=None,
            )
            sab_pen = self._match_context.performance_sabotage_penalty(carrier.side) if self._match_context else 0.0
            shot_result = resolve_shot(
                target, gk, recovering_def, ZoneCol.FINAL_THIRD, ZoneRow.CENTER, att_tactics, sabotage_penalty=sab_pen
            )

            state._inc(carrier.side, "shots")
            state._inc(carrier.side, "xg", xg_val)

            if shot_result.success:
                self._register_goal(
                    state, target, carrier, minute, att_name, def_name, xg_val,
                    desc=f"runs through on goal and finishes past the keeper!",
                )
                return action, True, None
            else:
                self._register_shot_miss(state, target, shot_result, minute, att_name, gk)
                if shot_result.detail == "saved":
                    # Possible corner from save
                    if random.random() < 0.35:
                        state._inc(carrier.side, "corners")
                        self._do_set_piece_corner(state, attackers, defenders, att_tactics, def_tactics, gk, att_name, def_name, minute)
                return action, True, None
        else:
            # Failed through ball
            self.partnership_tracker.record_pass(carrier.player_id, target.player_id, False)
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            action.success = False
            return action, True, None

    def _do_chain_switch_play(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Long diagonal ball to the opposite wing."""
        action.action_type = "switch_play"

        # Find player on opposite wing
        current_row = carrier.zone_row
        target_row = ZoneRow.RIGHT if current_row == ZoneRow.LEFT else ZoneRow.LEFT
        if current_row == ZoneRow.CENTER:
            target_row = random.choice([ZoneRow.LEFT, ZoneRow.RIGHT])

        candidates = [
            p for p in attackers
            if p != carrier and p.is_on_pitch and not p.is_gk
            and p.zone_row == target_row
        ]
        if not candidates:
            candidates = [p for p in attackers if p != carrier and p.is_on_pitch and not p.is_gk]
        if not candidates:
            action.success = False
            return action, False, None

        target = candidates[0]
        action.target = target
        action.zone_to = (target.zone_col, target.zone_row)

        # Uses long_passing heavily
        dist = zone_distance(action.zone_from, action.zone_to)
        dist = max(dist, 3.0)  # always a long ball

        pass_result = resolve_pass(carrier, target, nearest_def, dist, att_tactics)
        action.success = pass_result.success
        action.result = pass_result

        carrier.passes_attempted += 1
        state._inc(carrier.side, "passes")
        self.partnership_tracker.record_pass(carrier.player_id, target.player_id, pass_result.success)

        if pass_result.success:
            carrier.passes_completed += 1
            state._inc(carrier.side, "passes_completed")
            state.ball_zone_col = target.zone_col
            state.ball_zone_row = target.zone_row
            state.commentary.append(
                f"{minute}' {carrier.name} switches the play to {target.name} on the {'left' if target_row == ZoneRow.LEFT else 'right'}."
            )
            return action, False, target
        else:
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            return action, True, None

    def _do_chain_dribble(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Dribble past a defender."""
        action.action_type = "dribble"

        dribble_result = resolve_dribble(carrier, nearest_def, att_tactics)
        action.success = dribble_result.success
        action.result = dribble_result

        state._inc(carrier.side, "dribbles")
        if dribble_result.success:
            state._inc(carrier.side, "dribbles_completed")
            state._update_momentum(carrier.side, "dribble_completed")
            # Advance zone
            if carrier.side == "home":
                new_col = min(N_COLS - 1, carrier.zone_col + 1)
            else:
                new_col = max(0, carrier.zone_col - 1)
            carrier.zone_col = new_col
            state.ball_zone_col = new_col

            # Sprint cost
            carrier.stamina_current = max(0, carrier.stamina_current - FATIGUE_SPRINT_COST * 3)

            return action, False, carrier
        else:
            # Foul check
            if dribble_result.is_foul:
                return self._handle_foul(
                    state, nearest_def, carrier, dribble_result,
                    att_tactics, def_tactics, attackers, defenders,
                    att_name, def_name, minute,
                    action,
                )
            # Dispossessed — turnover
            if nearest_def:
                state._inc(nearest_def.side, "tackles")
                state._inc(nearest_def.side, "tackles_won")
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            return action, True, None

    def _do_chain_shot(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute, gk,
        assist_type="open_play",
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Take a shot on goal."""
        action.action_type = "shot"

        att_col = carrier.zone_col if carrier.side == "home" else (N_COLS - 1 - carrier.zone_col)
        defenders_nearby = self._count_defenders_nearby(carrier, defenders)

        xg_val = self.xg_model.calculate(
            zone_col=att_col, zone_row=carrier.zone_row,
            body_part="foot", assist_type=assist_type,
            is_counter=(state.get_momentum(carrier.side) > 0.15),
            defenders_in_path=defenders_nearby,
        )

        sab_pen = self._match_context.performance_sabotage_penalty(carrier.side) if self._match_context else 0.0
        shot_result = resolve_shot(
            carrier, gk, nearest_def,
            att_col, carrier.zone_row,
            att_tactics,
            sabotage_penalty=sab_pen,
        )
        action.success = shot_result.success
        action.result = shot_result

        state._inc(carrier.side, "shots")
        state._inc(carrier.side, "xg", xg_val)

        if shot_result.success:
            # Find assister — last player who passed to carrier in this possession
            assister = self._find_last_passer(state, carrier)
            self._register_goal(
                state, carrier, assister, minute, att_name, def_name, xg_val,
            )
        else:
            self._register_shot_miss(state, carrier, shot_result, minute, att_name, gk)
            # Match Situations: Missed Penalty
            if action.action_type == "penalty":
                self._trigger_situation(state, "handle_missed_penalty", player_id=carrier.player_id, minute=minute)
            
            # Corner chance on saved / blocked shots
            if shot_result.detail in ("saved", "blocked") and random.random() < 0.30:
                state._inc(carrier.side, "corners")
                self._do_set_piece_corner(
                    state, attackers, defenders, att_tactics, def_tactics, gk,
                    att_name, def_name, minute,
                )

        return action, True, None

    def _do_chain_cross(
        self, action, carrier, state, attackers, defenders,
        att_tactics, def_tactics, att_name, def_name, minute, gk,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Cross into the box."""
        action.action_type = "cross"

        # Target: best aerial threat
        targets = [p for p in attackers if p != carrier and not p.is_gk and p.is_on_pitch]
        if not targets:
            action.success = False
            return action, True, None

        target = max(targets, key=lambda p: (
            p.effective("heading_accuracy") + p.effective("jumping") + p.effective("positioning")
        ))

        # Defender marking the target
        markers = [p for p in defenders if not p.is_gk]
        marker = max(markers, key=lambda p: (
            p.effective("heading_accuracy") + p.effective("jumping") + p.effective("marking")
        )) if markers else None

        cross_result = resolve_cross(carrier, target, marker, att_tactics)
        action.result = cross_result
        action.target = target

        state._inc(carrier.side, "crosses")
        if cross_result.success:
            state._inc(carrier.side, "crosses_completed")
        else:
            # Cross blocked / intercepted — corner or clearance
            if marker:
                marker.clearances += 1
                state._inc(marker.side, "clearances")
            if random.random() < 0.25:
                state._inc(carrier.side, "corners")
                self._do_set_piece_corner(
                    state, attackers, defenders, att_tactics, def_tactics, gk,
                    att_name, def_name, minute,
                )
            action.success = False
            return action, True, None

        # Cross found a man — header attempt
        carrier.key_passes += 1
        state._inc(carrier.side, "key_passes")

        header_result = resolve_header(target, gk, marker, att_tactics)
        xg_val = self.xg_model.calculate(
            zone_col=ZoneCol.FINAL_THIRD, zone_row=ZoneRow.CENTER,
            body_part="head", assist_type="cross",
        )
        state._inc(carrier.side, "shots")
        state._inc(carrier.side, "xg", xg_val)

        if header_result.success:
            carrier.assists += 1
            carrier.rating_points += 0.3
            carrier.rating_events += 1
            self._register_goal(
                state, target, carrier, minute, att_name, def_name, xg_val,
                desc=f"heads it in from {carrier.name}'s cross!",
            )
            action.success = True
        else:
            self._register_shot_miss(state, target, header_result, minute, att_name, gk)
            action.success = False

        return action, True, None

    def _do_chain_one_two(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """One-two (wall pass) to bypass a defender."""
        action.action_type = "one_two"

        # Find nearby partner
        candidates = [
            p for p in attackers
            if p != carrier and p.is_on_pitch and not p.is_gk
            and zone_distance((carrier.zone_col, carrier.zone_row), (p.zone_col, p.zone_row)) <= 2
        ]
        if not candidates:
            # Fall back to a regular pass
            return self._do_chain_pass(
                action, carrier, state, attackers, defenders, nearest_def,
                att_tactics, def_tactics, att_name, def_name, minute,
            )

        # Prefer chemistry partner
        partner = self.partnership_tracker.get_preferred_partner(carrier.player_id, candidates)
        if partner is None:
            partner = random.choice(candidates)

        action.target = partner

        # Chemistry bonus
        chem = self.partnership_tracker.get_chemistry(carrier.player_id, partner.player_id)
        bonus = chem * 10.0

        # First pass
        first_pass_chance = clamp(
            (carrier.effective("short_passing") * 0.3 + carrier.effective("vision") * 0.2
             + partner.effective("positioning") * 0.2 + bonus) / 99.0,
            0.15, 0.80,
        )
        # Return pass
        return_pass_chance = clamp(
            (partner.effective("short_passing") * 0.3 + partner.effective("vision") * 0.2) / 99.0,
            0.20, 0.85,
        )

        carrier.passes_attempted += 1
        state._inc(carrier.side, "passes")

        if random.random() < first_pass_chance and random.random() < return_pass_chance:
            # Success! Carrier gets the ball back in an advanced position
            carrier.passes_completed += 1
            partner.passes_attempted += 1
            partner.passes_completed += 1
            state._inc(carrier.side, "passes", 1)  # return pass
            state._inc(carrier.side, "passes_completed", 2)  # both
            self.partnership_tracker.record_pass(carrier.player_id, partner.player_id, True)
            self.partnership_tracker.record_pass(partner.player_id, carrier.player_id, True)

            # Advance position
            if carrier.side == "home":
                carrier.zone_col = min(N_COLS - 1, carrier.zone_col + 1)
            else:
                carrier.zone_col = max(0, carrier.zone_col - 1)
            state.ball_zone_col = carrier.zone_col

            state.commentary.append(
                f"{minute}' Neat one-two between {carrier.name} and {partner.name}!"
            )
            action.success = True
            return action, False, carrier
        else:
            self.partnership_tracker.record_pass(carrier.player_id, partner.player_id, False)
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            action.success = False
            return action, True, None

    def _do_chain_hold_up(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, att_name, def_name, minute,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Hold-up play: carrier shields ball, waits for support."""
        action.action_type = "hold_up"

        # Success depends on strength + balance vs defender pressure
        hold_quality = (
            carrier.effective("strength") * 0.35
            + carrier.effective("balance") * 0.25
            + carrier.effective("ball_control") * 0.25
            + carrier.effective("composure") * 0.15
        )

        challenge = 0.0
        if nearest_def:
            challenge = (
                nearest_def.effective("strength") * 0.3
                + nearest_def.effective("aggression") * 0.2
                + nearest_def.effective("standing_tackle") * 0.2
            )

        success_chance = clamp((hold_quality - challenge * 0.4) / 99.0, 0.20, 0.80)

        if random.random() < success_chance:
            # Held it up — now find a supporting runner
            supporters = [
                p for p in attackers
                if p != carrier and p.is_on_pitch and not p.is_gk
                and zone_distance((carrier.zone_col, carrier.zone_row), (p.zone_col, p.zone_row)) <= 2
            ]
            if supporters:
                target = random.choice(supporters)
                action.target = target
                action.success = True
                state.ball_zone_col = target.zone_col
                state.ball_zone_row = target.zone_row
                return action, False, target
            else:
                action.success = True
                return action, False, carrier
        else:
            # Lost it
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            action.success = False
            return action, True, None

    def _do_chain_lay_off(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Lay-off: short pass back to a supporting midfielder in space."""
        action.action_type = "lay_off"

        # Find midfielder behind the ball
        candidates = [
            p for p in attackers
            if p != carrier and p.is_on_pitch and not p.is_gk
            and p.position in ("CM", "CDM", "CAM", "LM", "RM")
        ]
        if not candidates:
            candidates = [p for p in attackers if p != carrier and p.is_on_pitch and not p.is_gk]
        if not candidates:
            action.success = False
            return action, False, None

        target = random.choice(candidates[:3])
        action.target = target
        action.zone_to = (target.zone_col, target.zone_row)

        dist = zone_distance(action.zone_from, action.zone_to)

        sab_pen = self._match_context.performance_sabotage_penalty(carrier.side) if self._match_context else 0.0
        pass_result = resolve_pass(carrier, target, nearest_def, min(dist, 2.0), att_tactics, sabotage_penalty=sab_pen)
        action.success = pass_result.success
        carrier.passes_attempted += 1
        state._inc(carrier.side, "passes")
        self.partnership_tracker.record_pass(carrier.player_id, target.player_id, pass_result.success)

        if pass_result.success:
            carrier.passes_completed += 1
            state._inc(carrier.side, "passes_completed")
            state.ball_zone_col = target.zone_col
            state.ball_zone_row = target.zone_row
            return action, False, target
        else:
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            return action, True, None

    def _do_chain_play_out(
        self, action, carrier, state, attackers, defenders, nearest_def,
        att_tactics, def_tactics, att_name, def_name, minute,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Play out from the back / GK distribution."""
        action.action_type = "play_out"

        # Find a defender to pass to
        targets = [
            p for p in attackers
            if p != carrier and p.is_on_pitch and not p.is_gk
            and p.position in ("CB", "LB", "RB", "CDM")
        ]
        if not targets:
            targets = [p for p in attackers if p != carrier and p.is_on_pitch and not p.is_gk]
        if not targets:
            action.success = False
            return action, False, None

        target = random.choice(targets[:3])
        action.target = target
        action.zone_to = (target.zone_col, target.zone_row)

        dist = zone_distance(action.zone_from, action.zone_to)

        # Risky if opponent is pressing high
        press_risk = 0.0
        if def_tactics.pressing in ("high", "very_high"):
            press_risk = 0.10

        sab_pen = self._match_context.performance_sabotage_penalty(carrier.side) if self._match_context else 0.0
        pass_result = resolve_pass(carrier, target, nearest_def, dist, att_tactics, sabotage_penalty=sab_pen)
        carrier.passes_attempted += 1
        state._inc(carrier.side, "passes")

        # Extra risk from pressing
        if pass_result.success and random.random() < press_risk:
            pass_result = ResolutionResult(success=False)  # Pressed into error

        action.success = pass_result.success
        self.partnership_tracker.record_pass(carrier.player_id, target.player_id, pass_result.success)

        if pass_result.success:
            carrier.passes_completed += 1
            state._inc(carrier.side, "passes_completed")
            state.ball_zone_col = target.zone_col
            state.ball_zone_row = target.zone_row
            return action, False, target
        else:
            state._update_momentum(carrier.side, "turnover")
            self._change_possession(state)
            state.commentary.append(
                f"{minute}' Mistake playing out from the back! {def_name} win it in a dangerous area."
            )
            return action, True, None

    # ── Set piece handling ────────────────────────────────────────────────

    def _do_set_piece_corner(
        self, state, attackers, defenders, att_tactics, def_tactics, gk,
        att_name, def_name, minute,
    ) -> None:
        """Execute a corner kick routine."""
        opp_gk = gk
        outcome, result, scorer, assister = self.set_piece_engine.resolve_corner(
            attackers, defenders, att_tactics, def_tactics, opp_gk,
        )
        side = attackers[0].side if attackers else "home"

        if outcome == "goal" and scorer and result:
            xg_val = self.xg_model.calculate(
                zone_col=ZoneCol.FINAL_THIRD, zone_row=ZoneRow.CENTER,
                body_part="head", assist_type="corner",
            )
            state._inc(side, "xg", xg_val)
            self._register_goal(
                state, scorer, assister, minute,
                att_name, def_name, xg_val,
                desc=f"heads home from the corner!",
            )
        elif outcome == "saved" and result:
            state.commentary.append(f"{minute}' Header from the corner — saved!")
        elif outcome == "short_won":
            pass  # play continues
        else:
            state.commentary.append(f"{minute}' Corner cleared by {def_name}.")

    def _handle_foul(
        self, state, fouler, victim, dribble_result,
        att_tactics, def_tactics, attackers, defenders,
        att_name, def_name, minute, action,
    ) -> tuple[Action, bool, Optional[PlayerInMatch]]:
        """Handle a foul: cards, free kicks, penalties."""
        side = victim.side

        state._inc(fouler.side, "fouls")
        state._update_momentum(side, "free_kick_won")

        # Cards
        if dribble_result.is_red:
            fouler.red_card = True
            fouler.is_on_pitch = False
            state._inc(fouler.side, "red_cards")
            state._update_momentum(fouler.side, "red_card")
            state.commentary.append(
                f"{minute}' RED CARD! {fouler.name} is sent off for a terrible foul on {victim.name}!"
            )
            # Match Situations: Red Card
            self._trigger_situation(state, "handle_red_card_incident", player_id=fouler.player_id, incident_type="straight_red", minute=minute)
            if minute < 20:
                self._trigger_situation(state, "handle_early_red_card", player_id=fouler.player_id, minute=minute)
        elif dribble_result.is_yellow:
            fouler.yellow_cards += 1
            state._inc(fouler.side, "yellow_cards")
            state._update_momentum(fouler.side, "yellow_card")
            if fouler.yellow_cards >= 2:
                fouler.red_card = True
                fouler.is_on_pitch = False
                state._inc(fouler.side, "red_cards")
                state.commentary.append(
                    f"{minute}' Second yellow for {fouler.name}! He's off!"
                )
                # Match Situations: Red Card (Second Yellow)
                self._trigger_situation(state, "handle_red_card_incident", player_id=fouler.player_id, incident_type="second_yellow", minute=minute)
            else:
                state.commentary.append(
                    f"{minute}' {fouler.name} is booked for the foul on {victim.name}."
                )

        # Determine if penalty or free kick
        att_col = victim.zone_col if victim.side == "home" else (N_COLS - 1 - victim.zone_col)
        gk = state.get_gk("away" if side == "home" else "home")

        if att_col >= ZoneCol.FINAL_THIRD and victim.zone_row == ZoneRow.CENTER:
            # Penalty!
            state.commentary.append(f"{minute}' PENALTY to {att_name}!")
            outcome, pen_result, scorer = self.set_piece_engine.resolve_penalty_kick(
                attackers, gk, att_tactics,
            )
            state._inc(side, "shots")
            state._inc(side, "xg", pen_result.xg_value)

            if pen_result.success and scorer:
                self._register_goal(
                    state, scorer, None, minute, att_name, def_name,
                    pen_result.xg_value, desc="scores from the penalty spot!",
                )
            else:
                self._register_shot_miss(state, attackers[0], pen_result, minute, att_name, gk)
                # Match Situations: Missed Penalty
                self._trigger_situation(state, "handle_missed_penalty", player_id=attackers[0].player_id, minute=minute)
        elif att_col >= ZoneCol.ATTACK:
            # Dangerous free kick
            state.commentary.append(f"{minute}' Free kick to {att_name} in a dangerous area.")
            outcome, fk_result, scorer, assister = self.set_piece_engine.resolve_free_kick_situation(
                attackers, defenders, att_tactics, gk, att_col,
            )
            if fk_result:
                state._inc(side, "shots")
                state._inc(side, "xg", fk_result.xg_value)
                if fk_result.success and scorer:
                    self._register_goal(
                        state, scorer, assister, minute, att_name, def_name,
                        fk_result.xg_value, desc="scores from the free kick!",
                    )
                else:
                    self._register_shot_miss(state, scorer or attackers[0], fk_result, minute, att_name, gk)

        action.success = False
        return action, True, None

    # ── Goal & shot registration ──────────────────────────────────────────

    def _register_goal(
        self,
        state: MatchState,
        scorer: PlayerInMatch,
        assister: Optional[PlayerInMatch],
        minute: int,
        att_name: str,
        def_name: str,
        xg_val: float,
        desc: str = "scores!",
    ) -> None:
        """Register a goal in the match state."""
        side = scorer.side
        state._inc(side, "goals")
        state._inc(side, "sot")
        state._update_momentum(side, "goal")
        opp_side = "away" if side == "home" else "home"
        state._update_momentum(opp_side, "concede")

        # Match Situations: Late Goal
        if minute >= 87:
            score_diff = state.home_goals - state.away_goals
            is_comeback = (side == "home" and score_diff == 1) or (side == "away" and score_diff == -1)
            self._trigger_situation(state, "handle_late_goal", player_id=scorer.player_id, minute=minute, is_comeback=is_comeback)

        # Match Situations: Defensive Collapse (3 goals in 15 mins)
        recent_goals = [e for e in state.events if e["type"] == "goal" and e["side"] == side and minute - e["minute"] <= 15]
        if len(recent_goals) >= 3:
             self._trigger_situation(state, "handle_defensive_collapse", minute=minute)

        # Match Situations: Goalkeeper Error
        # If xG was very low but it was a goal, it might be an error (simplified)
        if xg_val < 0.05 and random.random() < 0.4:
            gk = state.get_gk(opp_side)
            if gk:
                self._trigger_situation(state, "handle_goalkeeper_error", player_id=gk.player_id, minute=minute)

        own_goals = state.home_goals if side == "home" else state.away_goals
        opp_goals = state.away_goals if side == "home" else state.home_goals

        # Commentary
        assist_text = f" (assist: {assister.name})" if assister else ""
        score_line = f"{state.home_goals}-{state.away_goals}"
        state.commentary.append(
            f"{minute}' GOAL! {scorer.name} {desc}{assist_text} [{score_line}]"
        )

        # Event record
        state.events.append({
            "type": "goal", "minute": minute,
            "player": scorer.name, "player_id": scorer.player_id,
            "side": side,
            "assist": assister.name if assister else None,
            "assist_id": assister.player_id if assister else None,
            "xg": round(xg_val, 2),
            "home_goals": state.home_goals,
            "away_goals": state.away_goals,
        })

        # Late goal drama
        if minute >= 85:
            state.commentary.append(f"{minute}' A LATE GOAL! The crowd goes wild!")
        if own_goals == opp_goals:
            state.commentary.append(f"{minute}' It's an equaliser!")
        if own_goals == opp_goals + 1 and minute >= 75:
            state.commentary.append(f"{minute}' What a time to take the lead!")

    def _trigger_situation(self, state, method_name, **kwargs):
        """Helper to trigger MatchSituationEngine and apply results to MatchState."""
        if not self._match_context or not hasattr(self._match_context, 'session'):
            return

        session = self._match_context.session
        if session is None:
            return

        # Find the player's club_id if possible
        player_id = kwargs.get('player_id')
        c_id = 0
        if player_id:
            from fm.db.models import Player
            p_db = session.get(Player, player_id)
            if p_db:
                c_id = p_db.club_id

        # Call the situation engine
        method = getattr(MatchSituationEngine, method_name, None)
        if method:
            # Call and get results
            result = method(
                session=session,
                club_id=c_id,
                season=self._match_context.season_year,
                matchday=self._match_context.matchday,
                **kwargs
            )
            
            # Apply results (e.g. momentum)
            if result and "momentum_change" in result:
                 # result["momentum_change"] is usually a float
                 pass
            
            # News and commentary
            if result and "news" in result:
                state.commentary.append(f"HOT NEWS: {result['news']['title']}")

    def _register_shot_miss(
        self,
        state: MatchState,
        shooter: PlayerInMatch,
        result: ResolutionResult,
        minute: int,
        att_name: str,
        gk: Optional[PlayerInMatch],
    ) -> None:
        """Register a missed shot."""
        side = shooter.side
        detail = result.detail

        if detail == "saved":
            state._inc(side, "sot")
            state._update_momentum(side, "shot_on_target")
            if gk:
                opp_side = "away" if side == "home" else "home"
                state._inc(opp_side, "saves")
                state._update_momentum(opp_side, "save")
            state.commentary.append(f"{minute}' {shooter.name} forces a save from the keeper!")
        elif detail == "blocked":
            state._inc(side, "shots_blocked")
            state.commentary.append(f"{minute}' {shooter.name}'s shot is blocked!")
        elif detail == "woodwork":
            state._inc(side, "woodwork")
            state.commentary.append(f"{minute}' {shooter.name} hits the post! So close!")
        elif detail in ("off_target", "headed_wide"):
            state.commentary.append(f"{minute}' {shooter.name} fires wide.")

        state.events.append({
            "type": "shot", "minute": minute,
            "player": shooter.name, "player_id": shooter.player_id,
            "side": side, "detail": detail,
        })

    # ── Helper methods ────────────────────────────────────────────────────

    def _apply_match_context(
        self,
        home_players: list[PlayerInMatch],
        away_players: list[PlayerInMatch],
        ctx,
    ) -> None:
        """Apply MatchContext modifiers to all players."""
        home_kwargs = dict(
            morale_mod=ctx.home_morale_mod,
            form_mod=ctx.home_form_mod,
            sharpness=ctx.home_sharpness,
            cohesion_mod=ctx.home_cohesion_mod,
            home_boost=ctx.home_advantage,
            importance_mod=ctx.importance,
            weather_pass_pen=ctx.weather_passing_penalty(),
            weather_pace_pen=ctx.weather_pace_penalty(),
            weather_shoot_mod=ctx.weather_shooting_mod(),
            pitch_dribble_pen=ctx.pitch_dribble_penalty(),
        )
        away_kwargs = dict(
            morale_mod=ctx.away_morale_mod,
            form_mod=ctx.away_form_mod,
            sharpness=ctx.away_sharpness,
            cohesion_mod=ctx.away_cohesion_mod,
            home_boost=0.0,
            importance_mod=ctx.importance,
            weather_pass_pen=ctx.weather_passing_penalty(),
            weather_pace_pen=ctx.weather_pace_penalty(),
            weather_shoot_mod=ctx.weather_shooting_mod(),
            pitch_dribble_pen=ctx.pitch_dribble_penalty(),
        )
        for p in home_players:
            p.apply_context(**home_kwargs)
        for p in away_players:
            p.apply_context(**away_kwargs)

        # ── Map Chemistry Partners ──
        if hasattr(ctx, "player_relationships"):
            all_players = home_players + away_players
            p_map = {p.player_id: p for p in all_players}
            
            for p1_id, p2_id, rel_type, strength in ctx.player_relationships:
                if p1_id in p_map and p2_id in p_map:
                    # Only map if they are on the same side (for now, mainly positive)
                    p1 = p_map[p1_id]
                    p2 = p_map[p2_id]
                    if p1.side == p2.side:
                        p1.chemistry_partners[p2_id] = strength
                        p2.chemistry_partners[p1_id] = strength

    def _assign_zones(
        self,
        state: MatchState,
        h_tac: TacticalContext,
        a_tac: TacticalContext,
    ) -> None:
        """Assign zone positions based on formation and ball position."""
        for side, tac, players in [
            ("home", h_tac, state.home_players),
            ("away", a_tac, state.away_players),
        ]:
            is_attacking = state.ball_side == side
            zones = tac.attacking_zones() if is_attacking else tac.defending_zones()
            outfield = [p for p in players if not p.is_gk and p.is_on_pitch]

            # GK always at own goal
            for p in players:
                if p.is_gk:
                    p.zone_col = 0 if side == "home" else N_COLS - 1
                    p.zone_row = ZoneRow.CENTER

            # 1. Fetch role assignments (outfield)
            roles = tac.roles if hasattr(tac, "roles") else ["CB"]*4 + ["CM"]*4 + ["ST"]*2

            for i, p in enumerate(outfield):
                if i < len(zones):
                    col, row = zones[i]
                    
                    # Track role on the player object
                    if i < len(roles):
                        p.role = roles[i]
                    
                    # Apply role offsets if attacking
                    if is_attacking:
                        c_off, r_off = get_role_offset(p.role, is_attacking=True)
                        col = clamp(col + c_off, 0, N_COLS - 1)
                        row = clamp(row + r_off, 0, N_ROWS - 1)

                    if side == "away":
                        col = N_COLS - 1 - col
                    p.zone_col = col
                    p.zone_row = row

    def _refresh_pitch(self, state: MatchState) -> None:
        """Clear and re-place players on the pitch grid."""
        self.pitch.clear_all()
        self.pitch.place_players(
            [p for p in state.home_players if p.is_on_pitch], "home",
        )
        self.pitch.place_players(
            [p for p in state.away_players if p.is_on_pitch], "away",
        )

    def _pick_initial_carrier(
        self,
        attackers: list[PlayerInMatch],
        phase: MatchPhase,
        state: MatchState,
    ) -> PlayerInMatch:
        """Pick who starts with the ball based on phase."""
        if phase == MatchPhase.BUILDUP:
            # GK or centre backs
            gk = [p for p in attackers if p.is_gk]
            if gk:
                return gk[0]
            cbs = [p for p in attackers if p.position in ("CB", "LB", "RB")]
            if cbs:
                return random.choice(cbs)
        elif phase in (MatchPhase.ESTABLISHED_ATTACK, MatchPhase.FINAL_THIRD):
            mids = [p for p in attackers if p.position in ("CM", "CDM", "CAM", "LM", "RM")]
            if mids:
                return random.choice(mids)
        elif phase == MatchPhase.COUNTER:
            fast = sorted(attackers, key=lambda p: p.effective("pace"), reverse=True)
            return fast[0] if fast else random.choice(attackers)

        return random.choice(attackers)

    def _nearest_defender(
        self,
        carrier: PlayerInMatch,
        defenders: list[PlayerInMatch],
    ) -> Optional[PlayerInMatch]:
        """Find the nearest active defender to the ball carrier."""
        if not defenders:
            return None
        return min(
            [d for d in defenders if d.is_on_pitch and not d.red_card and not d.is_gk],
            key=lambda d: zone_distance(
                (carrier.zone_col, carrier.zone_row), (d.zone_col, d.zone_row),
            ),
            default=None,
        )

    def _count_defenders_nearby(
        self,
        carrier: PlayerInMatch,
        defenders: list[PlayerInMatch],
    ) -> int:
        """Count defenders within 1 zone of the carrier."""
        count = 0
        for d in defenders:
            if not d.is_on_pitch or d.red_card or d.is_gk:
                continue
            if zone_distance(
                (carrier.zone_col, carrier.zone_row), (d.zone_col, d.zone_row),
            ) <= 1.5:
                count += 1
        return count

    def _find_interceptor(
        self,
        passer: PlayerInMatch,
        target: PlayerInMatch,
        defenders: list[PlayerInMatch],
        pass_distance: float,
    ) -> Optional[PlayerInMatch]:
        """Find a defender who might intercept this pass."""
        # Only defenders near the passing lane can intercept
        mid_col = (passer.zone_col + target.zone_col) / 2
        mid_row = (passer.zone_row + target.zone_row) / 2

        candidates = []
        for d in defenders:
            if not d.is_on_pitch or d.red_card or d.is_gk:
                continue
            dist = abs(d.zone_col - mid_col) + abs(d.zone_row - mid_row)
            if dist <= 1.5:
                candidates.append(d)

        if not candidates:
            return None

        # Best interceptor by attribute
        return max(candidates, key=lambda d: (
            d.effective("interceptions") * 0.4
            + d.effective("positioning") * 0.3
            + d.effective("reactions") * 0.3
        ))

    def _find_last_passer(
        self,
        state: MatchState,
        scorer: PlayerInMatch,
    ) -> Optional[PlayerInMatch]:
        """Try to find who assisted the scorer from the pass network."""
        network = self.partnership_tracker.get_pass_network()
        best_passes = 0
        assister = None
        for (from_id, to_id), count in network.items():
            if to_id == scorer.player_id and count > best_passes:
                best_passes = count
                # Find the player object
                all_players = state.home_players + state.away_players
                for p in all_players:
                    if p.player_id == from_id and p.side == scorer.side:
                        assister = p
                        break
        return assister

    def _change_possession(self, state: MatchState) -> None:
        """Switch possession to the other team."""
        state.ball_side = "away" if state.ball_side == "home" else "home"
        # Ball position stays roughly where it was
        state.ball_carrier = None

    def _classify_outcome(self, action: Action) -> str:
        """Classify how a possession chain ended."""
        if action.action_type == "shot":
            return "shot"
        if action.result and action.result.is_foul:
            return "foul"
        return "turnover"

    # ── Fatigue ───────────────────────────────────────────────────────────

    def _apply_fatigue(
        self,
        state: MatchState,
        minute: int,
        h_tac: TacticalContext,
        a_tac: TacticalContext,
    ) -> None:
        """Apply per-minute fatigue to all players."""
        weather_mult = 1.0
        if self._match_context is not None and hasattr(self._match_context, "weather_fatigue_multiplier"):
            weather_mult = self._match_context.weather_fatigue_multiplier()

        for side, tac, players in [
            ("home", h_tac, state.home_players),
            ("away", a_tac, state.away_players),
        ]:
            press_cost = max(0, tac.press_modifier) * 0.3
            tempo_cost = max(0, tac.tempo_modifier) * 0.2

            for p in players:
                if not p.is_on_pitch:
                    continue
                base_drain = FATIGUE_PER_MINUTE * weather_mult
                # High pressing and tempo cost more stamina
                base_drain += press_cost + tempo_cost
                # Stamina attribute reduces drain
                stamina_resist = p.stamina / 100.0 * 0.3
                drain = max(0.2, base_drain - stamina_resist)
                p.stamina_current = max(0, p.stamina_current - drain)
                p.minutes_played = minute
                p.distance_covered += random.uniform(0.10, 0.15)

    # ── Injuries ──────────────────────────────────────────────────────────

    def _check_injuries(
        self,
        state: MatchState,
        minute: int,
        h_name: str,
        a_name: str,
    ) -> None:
        """Check for injuries each minute."""
        for p in state.home_players + state.away_players:
            if not p.is_on_pitch or p.red_card:
                continue
            # Injury more likely when tired or older
            fatigue_risk = max(0, (50 - p.stamina_current) / 100.0) * 0.001
            chance = INJURY_BASE_CHANCE + fatigue_risk
            if random.random() < chance:
                name = h_name if p.side == "home" else a_name
                state.commentary.append(
                    f"{minute}' {p.name} ({name}) goes down injured and needs treatment."
                )
                p.stamina_current = max(0, p.stamina_current - 15)
                state.events.append({
                    "type": "injury", "minute": minute,
                    "player": p.name, "player_id": p.player_id,
                    "side": p.side,
                })

    # ── Auto substitutions ────────────────────────────────────────────────

    def _auto_subs(
        self,
        state: MatchState,
        minute: int,
        h_name: str,
        a_name: str,
    ) -> None:
        """AI substitutions for tired / injured players."""
        for side, players, subs, subs_made, name in [
            ("home", state.home_players, state.home_subs, state.home_subs_made, h_name),
            ("away", state.away_players, state.away_subs, state.away_subs_made, a_name),
        ]:
            if subs_made >= state.max_subs or not subs:
                continue

            # Find most tired outfield player
            tired = [
                p for p in players
                if p.is_on_pitch and not p.is_gk and not p.red_card
                and p.stamina_current < 35
            ]
            if not tired:
                continue

            tired.sort(key=lambda p: p.stamina_current)
            out_player = tired[0]

            # Find best available sub (match position if possible)
            best_sub = None
            for s in subs:
                if s.is_on_pitch:
                    continue
                if s.position == out_player.position:
                    best_sub = s
                    break
            if best_sub is None:
                for s in subs:
                    if not s.is_on_pitch:
                        best_sub = s
                        break
            if best_sub is None:
                continue

            # Make the sub
            out_player.is_on_pitch = False
            best_sub.is_on_pitch = True
            best_sub.side = side
            best_sub.zone_col = out_player.zone_col
            best_sub.zone_row = out_player.zone_row

            if side == "home":
                state.home_subs_made += 1
            else:
                state.away_subs_made += 1

            state.commentary.append(
                f"{minute}' Substitution for {name}: {best_sub.name} replaces {out_player.name}."
            )
            state.events.append({
                "type": "substitution", "minute": minute, "side": side,
                "player_on": best_sub.name, "player_on_id": best_sub.player_id,
                "player_off": out_player.name, "player_off_id": out_player.player_id,
            })
            # Match Situations: Young Player Debut
            self._trigger_situation(state, "handle_young_player_debut", player_id=best_sub.player_id, minute=minute)

    # ── Scorecard generation ──────────────────────────────────────────────

    def _generate_scorecard(self, state: MatchState, minute: int) -> Scorecard:
        """Generate a scorecard for the current interval."""
        return Scorecard(
            minute=minute,
            home_goals=state.home_goals,
            away_goals=state.away_goals,
            home_possession=state.home_possession_pct,
            away_possession=100.0 - state.home_possession_pct,
            home_shots=state.home_shots,
            away_shots=state.away_shots,
            home_sot=state.home_sot,
            away_sot=state.away_sot,
            home_xg=round(state.home_xg, 2),
            away_xg=round(state.away_xg, 2),
            home_passes=state.home_passes,
            away_passes=state.away_passes,
            home_fouls=state.home_fouls,
            away_fouls=state.away_fouls,
            home_corners=state.home_corners,
            away_corners=state.away_corners,
            events_text=list(state.commentary[-5:]),
            zone_heatmap_home=self.pitch.text_heatmap("home"),
            zone_heatmap_away=self.pitch.text_heatmap("away"),
        )

    # ── Final ratings ─────────────────────────────────────────────────────

    def _finalize_ratings(self, state: MatchState) -> None:
        """Calculate final match ratings for all players.

        The MatchRatingCalculator produces a single 3.0-10.0 rating based on
        accumulated match stats (goals, assists, tackles, etc.).  We set
        rating_events = 1 so that avg_rating == rating_points (the final
        calculated rating).  The per-event increments accumulated during the
        match are intentionally replaced here.
        """
        home_clean = state.away_goals == 0
        away_clean = state.home_goals == 0

        for p in state.home_players:
            p.rating_points = self.rating_calculator.calculate(p)
            if home_clean and (p.is_gk or p.position in ("CB", "LB", "RB", "LWB", "RWB")):
                p.rating_points = min(p.rating_points + 0.5, 10.0)
            # Reset events to 1 so avg_rating = rating_points (the final rating)
            p.rating_events = 1

        for p in state.away_players:
            p.rating_points = self.rating_calculator.calculate(p)
            if away_clean and (p.is_gk or p.position in ("CB", "LB", "RB", "LWB", "RWB")):
                p.rating_points = min(p.rating_points + 0.5, 10.0)
            p.rating_events = 1
