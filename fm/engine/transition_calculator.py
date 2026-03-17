"""Transition probability matrix builder for the Markov chain match engine.

This is the heart of the V3 engine: it builds and dynamically adjusts the
probability matrix that governs how possession chains flow from one state
to another.  Team attributes, tactical instructions, zone control, and
match context all influence the probabilities.
"""
from __future__ import annotations

from copy import deepcopy

from fm.engine.chain_states import ChainState
from fm.engine.tactics import TacticalContext
from fm.utils.helpers import clamp


# ── Base transition probabilities ─────────────────────────────────────────
# Realistic defaults calibrated to produce ~2.5 goals/match, ~12 shots/side,
# ~50% possession per side, and sensible chain lengths.

BASE_TRANSITIONS: dict[ChainState, dict[ChainState, float]] = {
    ChainState.GOAL_KICK: {
        ChainState.BUILDUP_DEEP: 0.70,
        ChainState.LONG_BALL: 0.20,
        ChainState.BUILDUP_MID: 0.10,
    },
    ChainState.BUILDUP_DEEP: {
        ChainState.BUILDUP_MID: 0.55,
        ChainState.TURNOVER: 0.15,
        ChainState.LONG_BALL: 0.15,
        ChainState.PRESS_TRIGGERED: 0.10,
        ChainState.PROGRESSION: 0.05,
    },
    ChainState.BUILDUP_MID: {
        ChainState.PROGRESSION: 0.35,
        ChainState.TURNOVER: 0.25,
        ChainState.LONG_BALL: 0.10,
        ChainState.BUILDUP_DEEP: 0.12,
        ChainState.CHANCE_CREATION: 0.08,
        ChainState.PRESS_TRIGGERED: 0.05,
        ChainState.CROSS: 0.05,
    },
    ChainState.PROGRESSION: {
        ChainState.CHANCE_CREATION: 0.30,
        ChainState.TURNOVER: 0.30,
        ChainState.CROSS: 0.15,
        ChainState.BUILDUP_MID: 0.10,
        ChainState.SHOT: 0.03,
        ChainState.SET_PIECE_FK_INDIRECT: 0.06,
        ChainState.SET_PIECE_CORNER: 0.06,
    },
    ChainState.CHANCE_CREATION: {
        ChainState.SHOT: 0.10,
        ChainState.CROSS: 0.12,
        ChainState.TURNOVER: 0.42,
        ChainState.PROGRESSION: 0.08,
        ChainState.SET_PIECE_FK_DIRECT: 0.05,
        ChainState.SET_PIECE_CORNER: 0.06,
        ChainState.PENALTY: 0.01,
        ChainState.SET_PIECE_FK_INDIRECT: 0.04,
        ChainState.BUILDUP_MID: 0.12,
    },
    ChainState.SHOT: {
        # SHOT→GOAL is handled by the resolver, not the matrix.
        # These transitions only matter if the chain doesn't break
        # after _handle_shot (which it now does).
        ChainState.GOAL: 0.0,
        ChainState.TURNOVER: 0.55,
        ChainState.SET_PIECE_CORNER: 0.25,
        ChainState.GOAL_KICK: 0.20,
    },
    ChainState.CROSS: {
        ChainState.SHOT: 0.15,
        ChainState.TURNOVER: 0.45,
        ChainState.SET_PIECE_CORNER: 0.15,
        ChainState.GOAL_KICK: 0.20,
        ChainState.SET_PIECE_FK_INDIRECT: 0.05,
    },
    ChainState.COUNTER_ATTACK: {
        ChainState.CHANCE_CREATION: 0.30,
        ChainState.SHOT: 0.08,
        ChainState.TURNOVER: 0.35,
        ChainState.PROGRESSION: 0.15,
        ChainState.CROSS: 0.12,
    },
    ChainState.LONG_BALL: {
        ChainState.TURNOVER: 0.40,
        ChainState.PROGRESSION: 0.25,
        ChainState.CHANCE_CREATION: 0.15,
        ChainState.CROSS: 0.10,
        ChainState.SET_PIECE_FK_INDIRECT: 0.05,
        ChainState.BUILDUP_MID: 0.05,
    },
    ChainState.PRESS_TRIGGERED: {
        ChainState.TURNOVER: 0.45,
        ChainState.COUNTER_ATTACK: 0.25,
        ChainState.CHANCE_CREATION: 0.10,
        ChainState.LONG_BALL: 0.10,
        ChainState.BUILDUP_DEEP: 0.10,
    },
    ChainState.TRANSITION: {
        ChainState.BUILDUP_DEEP: 0.30,
        ChainState.BUILDUP_MID: 0.25,
        ChainState.COUNTER_ATTACK: 0.15,
        ChainState.LONG_BALL: 0.10,
        ChainState.GOAL_KICK: 0.10,
        ChainState.PRESS_TRIGGERED: 0.10,
    },
}


class TransitionCalculator:
    """Builds and updates the transition probability matrix.

    The matrix is recomputed every *recompute_interval* game-minutes to
    reflect changing match conditions (fatigue, momentum, tactical shifts).
    """

    recompute_interval: int = 15  # game-minutes between recomputation

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_matrix(
        self,
        team_attrs: dict[str, float],
        tactics: TacticalContext,
        match_context: dict,
        zone_control: dict[tuple[int, int], float],
        opponent_tactics: TacticalContext | None = None,
    ) -> dict[ChainState, dict[ChainState, float]]:
        """Build the full transition matrix for one team's possession.

        Args:
            team_attrs: Averaged team attributes by area. Expected keys:
                ``"def_avg"``, ``"mid_avg"``, ``"att_avg"`` (0-99 scale).
            tactics: The possessing team's tactical context.
            match_context: Dict with keys like ``"momentum"`` (-1..1),
                ``"fatigue_avg"`` (0-100 stamina), ``"morale"`` (-1..1).
            zone_control: Mapping of ``(col, row)`` -> control ratio (0-1)
                for the possessing team.
            opponent_tactics: The opposing team's tactical context (used
                for interaction effects like high press vs short passing).

        Returns:
            A dict mapping each source ``ChainState`` to a dict of
            target ``ChainState`` -> probability.  Each row sums to 1.0.
        """
        matrix = deepcopy(BASE_TRANSITIONS)

        # --- Team attribute modifiers ---
        self._apply_team_attrs(matrix, team_attrs)

        # --- Tactical instruction modifiers ---
        self._apply_tactics(matrix, tactics, opponent_tactics)

        # --- Zone control influence ---
        self._apply_zone_control(matrix, zone_control)

        # --- Match context (momentum, fatigue, morale) ---
        self._apply_match_context(matrix, match_context)

        # --- Normalize every row to sum to 1.0 ---
        for state in matrix:
            matrix[state] = self._normalize_row(matrix[state])

        return matrix

    # ------------------------------------------------------------------
    # Internal modifiers
    # ------------------------------------------------------------------

    def _apply_team_attrs(
        self,
        matrix: dict[ChainState, dict[ChainState, float]],
        attrs: dict[str, float],
    ) -> None:
        """Modify matrix based on team attribute averages by zone."""
        def_avg = attrs.get("def_avg", 50) / 99.0
        mid_avg = attrs.get("mid_avg", 50) / 99.0
        att_avg = attrs.get("att_avg", 50) / 99.0

        # Strong midfield → better progression
        mid_bonus = (mid_avg - 0.5) * 0.15  # -0.075 to +0.075
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, mid_bonus)
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.TURNOVER, -mid_bonus * 0.6)

        # Strong attack → better chance creation and shot conversion
        att_bonus = (att_avg - 0.5) * 0.12
        self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.SHOT, att_bonus)
        self._adjust(matrix, ChainState.SHOT, ChainState.GOAL, att_bonus * 0.5)
        self._adjust(matrix, ChainState.PROGRESSION, ChainState.CHANCE_CREATION, att_bonus * 0.5)

        # Strong defence → better build-up from the back
        def_bonus = (def_avg - 0.5) * 0.10
        self._adjust(matrix, ChainState.BUILDUP_DEEP, ChainState.BUILDUP_MID, def_bonus)
        self._adjust(matrix, ChainState.BUILDUP_DEEP, ChainState.TURNOVER, -def_bonus * 0.5)

    def _apply_tactics(
        self,
        matrix: dict[ChainState, dict[ChainState, float]],
        tactics: TacticalContext,
        opponent_tactics: TacticalContext | None,
    ) -> None:
        """Apply tactical instruction effects to the matrix."""

        # --- Own pressing: higher pressing = more press triggers ---
        own_press = tactics.press_modifier
        self._adjust(matrix, ChainState.BUILDUP_DEEP, ChainState.PRESS_TRIGGERED, own_press * 0.12)
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PRESS_TRIGGERED, own_press * 0.08)

        # --- Pressing interaction ---
        opp_press = opponent_tactics.press_modifier if opponent_tactics else 0.0
        own_passing = tactics.passing_modifier

        # High opponent press vs short passing → harder to build from the back
        if opp_press > 0.10 and own_passing > 0.0:
            self._adjust(matrix, ChainState.BUILDUP_DEEP, ChainState.PRESS_TRIGGERED, 0.15)
            self._adjust(matrix, ChainState.BUILDUP_DEEP, ChainState.BUILDUP_MID, -0.10)

        # --- Mentality ---
        risk = tactics.risk_modifier
        # Attacking mentality: more shots, more risk
        self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.SHOT, risk * 0.10)
        self._adjust(matrix, ChainState.PROGRESSION, ChainState.CHANCE_CREATION, risk * 0.08)
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.TURNOVER, risk * 0.05)

        # --- Tempo ---
        tempo = tactics.tempo_modifier
        # Faster tempo: quicker progression but riskier
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, tempo * 0.06)
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.TURNOVER, tempo * 0.04)

        # --- Passing style ---
        passing = tactics.passing_modifier
        # Direct passing → more long balls, less controlled progression
        if passing < -0.03:  # direct or very_direct
            self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.LONG_BALL, 0.08)
            self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, -0.05)
        # Short passing → better controlled build-up
        elif passing > 0.05:
            self._adjust(matrix, ChainState.BUILDUP_DEEP, ChainState.BUILDUP_MID, 0.05)
            self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, 0.04)

        # --- Width ---
        width = tactics.width_modifier
        # Wide play → more crosses
        self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.CROSS, width * 0.10)
        if opponent_tactics and opponent_tactics.width_modifier < -0.05:
            # Wide play vs narrow defence → even more crossing opportunity
            self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.CROSS, 0.10)

        # --- Counter-attack ---
        if tactics.counter_attack:
            self._adjust(matrix, ChainState.TRANSITION, ChainState.COUNTER_ATTACK, 0.12)
            self._adjust(matrix, ChainState.PRESS_TRIGGERED, ChainState.COUNTER_ATTACK, 0.15)
            # Exploit high defensive line
            opp_def_line = opponent_tactics.defensive_line if opponent_tactics else None
            if opp_def_line == "high":
                self._adjust(matrix, ChainState.COUNTER_ATTACK, ChainState.CHANCE_CREATION, 0.10)

        # --- Defensive line ---
        if tactics.defensive_line == "high":
            # High line makes opponent counters more dangerous (handled in opp matrix)
            # For own possession: more aggressive, but also more turnovers recovered high
            self._adjust(matrix, ChainState.PRESS_TRIGGERED, ChainState.COUNTER_ATTACK, 0.05)
        elif tactics.defensive_line == "deep":
            # Low block: harder for opponent to progress through
            # (Applied when this is the opponent's matrix)
            pass

        # --- Play out from back ---
        if tactics.play_out_from_back:
            self._adjust(matrix, ChainState.GOAL_KICK, ChainState.BUILDUP_DEEP, 0.10)
            self._adjust(matrix, ChainState.GOAL_KICK, ChainState.LONG_BALL, -0.10)

        # --- Opponent low block (deep defensive line) ---
        if opponent_tactics and opponent_tactics.defensive_line == "deep":
            self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, -0.08)
            self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.SHOT, -0.05)

    def _apply_zone_control(
        self,
        matrix: dict[ChainState, dict[ChainState, float]],
        zone_control: dict[tuple[int, int], float],
    ) -> None:
        """Modify transitions based on zone control ratios."""
        if not zone_control:
            return

        # Average control in midfield zones (cols 2-3)
        mid_zones = [(c, r) for c in (2, 3) for r in (0, 1, 2)]
        mid_control = sum(zone_control.get(z, 0.5) for z in mid_zones) / max(len(mid_zones), 1)

        # Average control in attacking zones (cols 4-5)
        att_zones = [(c, r) for c in (4, 5) for r in (0, 1, 2)]
        att_control = sum(zone_control.get(z, 0.5) for z in att_zones) / max(len(att_zones), 1)

        # Midfield dominance → better progression
        mid_advantage = (mid_control - 0.5) * 0.20
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, mid_advantage)

        # 3v2 midfield overload (strong midfield control)
        if mid_control > 0.60:
            self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, 0.12)

        # Attacking zone control → better chance creation
        att_advantage = (att_control - 0.5) * 0.15
        self._adjust(matrix, ChainState.PROGRESSION, ChainState.CHANCE_CREATION, att_advantage)
        self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.SHOT, att_advantage * 0.5)

    def _apply_match_context(
        self,
        matrix: dict[ChainState, dict[ChainState, float]],
        ctx: dict,
    ) -> None:
        """Adjust for momentum, fatigue, and morale."""
        momentum = ctx.get("momentum", 0.0)
        fatigue_avg = ctx.get("fatigue_avg", 100.0)  # stamina remaining
        morale = ctx.get("morale", 0.0)

        # Momentum: positive momentum → better progression and finishing
        self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.PROGRESSION, momentum * 0.06)
        self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.SHOT, momentum * 0.05)
        self._adjust(matrix, ChainState.SHOT, ChainState.GOAL, momentum * 0.03)

        # Fatigue: low stamina → more turnovers, less progression
        stamina_deficit = (70.0 - fatigue_avg) / 100.0  # positive when tired
        if stamina_deficit > 0:
            self._adjust(matrix, ChainState.BUILDUP_MID, ChainState.TURNOVER, stamina_deficit * 0.15)
            self._adjust(matrix, ChainState.PROGRESSION, ChainState.TURNOVER, stamina_deficit * 0.12)
            self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.TURNOVER, stamina_deficit * 0.10)

        # Morale: affects composure in key moments
        self._adjust(matrix, ChainState.CHANCE_CREATION, ChainState.SHOT, morale * 0.04)
        self._adjust(matrix, ChainState.SHOT, ChainState.GOAL, morale * 0.02)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _adjust(
        matrix: dict[ChainState, dict[ChainState, float]],
        source: ChainState,
        target: ChainState,
        delta: float,
    ) -> None:
        """Safely adjust a single transition probability."""
        if source not in matrix:
            return
        row = matrix[source]
        if target not in row:
            # Only add if the delta is positive
            if delta > 0:
                row[target] = delta
            return
        row[target] = max(row[target] + delta, 0.001)

    @staticmethod
    def _normalize_row(row: dict[ChainState, float]) -> dict[ChainState, float]:
        """Normalize a probability row so it sums to 1.0."""
        total = sum(row.values())
        if total <= 0:
            # Fallback: uniform distribution
            n = len(row)
            return {k: 1.0 / n for k in row}
        return {k: v / total for k, v in row.items()}
