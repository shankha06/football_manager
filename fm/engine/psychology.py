"""Match psychology engine for the V3 Markov chain match engine.

Tracks momentum, crowd pressure, snowball effects after goals, and
individual player psychological modifiers.  The psychology engine feeds
back into the transition calculator to shift probabilities dynamically.
"""
from __future__ import annotations

from fm.engine.match_state import PlayerInMatch
from fm.utils.helpers import clamp


class PsychologyEngine:
    """Tracks and computes psychological effects during a match."""

    def __init__(self) -> None:
        self.momentum: dict[str, float] = {"home": 0.0, "away": 0.0}
        self.last_goal_minute: dict[str, int] = {"home": -10, "away": -10}

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------

    def process_event(self, event_type: str, side: str, minute: int) -> dict:
        """Process a match event and return psychology deltas.

        Args:
            event_type: One of "goal", "red_card", "save",
                "miss_big_chance", "yellow_card", "shot_on_target".
            side: "home" or "away" — the side the event happened *to*.
            minute: Current match minute.

        Returns:
            Dict with keys like ``"momentum_delta"``, etc.
        """
        other = "away" if side == "home" else "home"
        result: dict = {}

        if event_type == "goal":
            # Momentum spike for scoring side
            spike = 0.25 + min(0.10, (90 - minute) / 900.0)  # late goals slightly bigger
            self.momentum[side] = clamp(self.momentum[side] + spike, -1.0, 1.0)
            self.momentum[other] = clamp(self.momentum[other] - spike * 0.5, -1.0, 1.0)
            self.last_goal_minute[side] = minute
            result["momentum_delta"] = spike

        elif event_type == "red_card":
            self.momentum[side] = clamp(self.momentum[side] - 0.20, -1.0, 1.0)
            self.momentum[other] = clamp(self.momentum[other] + 0.10, -1.0, 1.0)
            result["momentum_delta"] = -0.20

        elif event_type == "save":
            self.momentum[side] = clamp(self.momentum[side] + 0.05, -1.0, 1.0)
            self.momentum[other] = clamp(self.momentum[other] - 0.03, -1.0, 1.0)
            result["momentum_delta"] = 0.05

        elif event_type == "miss_big_chance":
            self.momentum[side] = clamp(self.momentum[side] - 0.10, -1.0, 1.0)
            self.momentum[other] = clamp(self.momentum[other] + 0.05, -1.0, 1.0)
            result["momentum_delta"] = -0.10

        elif event_type == "yellow_card":
            self.momentum[side] = clamp(self.momentum[side] - 0.04, -1.0, 1.0)
            result["momentum_delta"] = -0.04

        elif event_type == "shot_on_target":
            self.momentum[side] = clamp(self.momentum[side] + 0.03, -1.0, 1.0)
            result["momentum_delta"] = 0.03

        return result

    # ------------------------------------------------------------------
    # Snowball / momentum queries
    # ------------------------------------------------------------------

    def get_snowball_bonus(self, side: str, minute: int) -> float:
        """Return a bonus to CHANCE_CREATION->SHOT if a goal was scored recently.

        If a goal was scored within the last 5 minutes, return up to +0.10
        with linear decay.
        """
        last = self.last_goal_minute.get(side, -10)
        minutes_since = minute - last
        if minutes_since < 0 or minutes_since > 5:
            return 0.0
        # Linear decay: 0.10 at minute 0, 0.0 at minute 5
        return 0.10 * (1.0 - minutes_since / 5.0)

    def get_crowd_pressure(
        self, side: str, is_home: bool, importance: float = 1.0,
    ) -> float:
        """Return a composure modifier from crowd pressure.

        Home crowd boosts composure for the home team (+) and reduces it
        for the away team (-).  Higher importance amplifies the effect.

        Returns:
            Float modifier to add to composure-related calculations.
            Positive = boost, negative = pressure.
        """
        base = 0.04 if is_home else -0.03
        return base * clamp(importance, 0.5, 2.0)

    def get_individual_modifier(
        self, player: PlayerInMatch, minute: int, importance: float = 1.0,
    ) -> dict[str, float]:
        """Compute individual psychological modifiers for a player.

        Returns:
            Dict with optional keys ``"composure_mod"``,
            ``"determination_bonus"``.
        """
        mods: dict[str, float] = {}

        # Big-match temperament
        if importance > 1.05:
            if player.big_match < 40:
                # Nervous player in a big match → composure penalty
                mods["composure_mod"] = -0.15
            elif player.big_match > 80:
                # Big-game player thrives
                mods["composure_mod"] = 0.08

        # Late game + losing → determination bonus
        is_losing = False
        if player.side == "home":
            is_losing = self.momentum.get("home", 0.0) < -0.15
        else:
            is_losing = self.momentum.get("away", 0.0) < -0.15

        if minute >= 75 and is_losing:
            det_factor = player.composure / 99.0 * 0.08
            mods["determination_bonus"] = det_factor

        return mods

    # ------------------------------------------------------------------
    # Team talk effects
    # ------------------------------------------------------------------

    def apply_team_talk_effects(
        self, players: list[PlayerInMatch], talk_type: str,
    ) -> None:
        """Apply pre-match team talk effects to all players.

        Effects persist for the whole match via the player's context
        modifier fields.

        Args:
            players: List of PlayerInMatch to modify.
            talk_type: One of "motivate", "calm", "criticize",
                "encourage", "demand", "praise".
        """
        for p in players:
            if talk_type == "motivate":
                p.morale_mod = clamp(p.morale_mod + 0.05, -0.10, 0.10)
                # Small composure boost from being fired up
                p.home_boost = clamp(p.home_boost + 0.02, 0.0, 0.15)

            elif talk_type == "calm":
                # Composure boost, slight aggression dampening
                p.home_boost = clamp(p.home_boost + 0.05, 0.0, 0.15)
                # Reduce recklessness (lower aggression penalty via morale)
                p.morale_mod = clamp(p.morale_mod + 0.01, -0.10, 0.10)

            elif talk_type == "criticize":
                # Can backfire on low-temperament players
                if p.temperament < 40:
                    p.morale_mod = clamp(p.morale_mod - 0.05, -0.10, 0.10)
                else:
                    # Tough players respond positively
                    p.morale_mod = clamp(p.morale_mod + 0.03, -0.10, 0.10)

            elif talk_type == "encourage":
                p.morale_mod = clamp(p.morale_mod + 0.03, -0.10, 0.10)

            elif talk_type == "demand":
                # High expectations — works for professionals
                if p.professionalism > 65:
                    p.morale_mod = clamp(p.morale_mod + 0.04, -0.10, 0.10)
                else:
                    p.morale_mod = clamp(p.morale_mod - 0.02, -0.10, 0.10)

            elif talk_type == "praise":
                p.morale_mod = clamp(p.morale_mod + 0.02, -0.10, 0.10)
                p.form_mod = clamp(p.form_mod + 0.02, -0.08, 0.08)

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    def decay_momentum(self, rate: float = 0.02) -> None:
        """Gradually pull momentum back towards zero.  Call each minute."""
        for side in ("home", "away"):
            m = self.momentum[side]
            if m > 0:
                self.momentum[side] = max(0.0, m - rate)
            elif m < 0:
                self.momentum[side] = min(0.0, m + rate)
