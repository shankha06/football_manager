"""Rules-based tactical effectiveness scorer."""

from __future__ import annotations

from typing import Dict, List


# Style counter matrix: how well attacker_style counters defender_style.
# Positive = good for attacker, negative = bad.
_STYLE_COUNTERS: dict[str, dict[str, float]] = {
    "high_press": {
        "short_passing": 15.0,   # pressing disrupts short passing
        "possession": 12.0,
        "long_ball": -10.0,      # long ball bypasses press
        "counter_attack": -8.0,  # counters exploit high line
        "high_press": 0.0,
        "balanced": 3.0,
    },
    "counter_attack": {
        "high_press": 12.0,      # exploits high line gaps
        "possession": 5.0,
        "short_passing": 3.0,
        "long_ball": -5.0,
        "counter_attack": 0.0,
        "balanced": 2.0,
    },
    "possession": {
        "long_ball": 10.0,       # keeps ball away from direct teams
        "counter_attack": 5.0,   # limits counter opportunities
        "balanced": 3.0,
        "high_press": -8.0,      # vulnerable to pressing
        "short_passing": 0.0,
        "possession": 0.0,
    },
    "long_ball": {
        "high_press": 10.0,      # bypasses press
        "possession": -5.0,
        "short_passing": -3.0,
        "counter_attack": 2.0,
        "long_ball": 0.0,
        "balanced": 1.0,
    },
    "short_passing": {
        "long_ball": 8.0,
        "balanced": 3.0,
        "counter_attack": 2.0,
        "high_press": -12.0,
        "possession": 0.0,
        "short_passing": 0.0,
    },
    "balanced": {
        "high_press": 2.0,
        "counter_attack": 0.0,
        "possession": 0.0,
        "long_ball": 0.0,
        "short_passing": 0.0,
        "balanced": 0.0,
    },
}

# Role-to-key-attribute mapping for suitability scoring.
_ROLE_ATTRIBUTES: dict[str, list[str]] = {
    "GK": ["diving", "reflexes", "positioning"],
    "CB": ["defending", "physicality", "heading"],
    "LB": ["pace", "defending", "crossing"],
    "RB": ["pace", "defending", "crossing"],
    "CDM": ["defending", "passing", "physicality"],
    "CM": ["passing", "dribbling", "stamina"],
    "CAM": ["passing", "dribbling", "shooting"],
    "LM": ["pace", "dribbling", "crossing"],
    "RM": ["pace", "dribbling", "crossing"],
    "LW": ["pace", "dribbling", "shooting"],
    "RW": ["pace", "dribbling", "shooting"],
    "ST": ["shooting", "finishing", "pace"],
    "CF": ["shooting", "passing", "dribbling"],
}

# Zone names used for overload calculations.
_ZONES = ["defence", "midfield", "attack", "left_flank", "right_flank"]


class TacticalScorer:
    """Rules-based tactical effectiveness scorer.

    Evaluates how well a team's tactics perform against an opponent,
    returning a score from 0 to 100. Three equally-weighted components:
      - Zone overload (numerical advantages in key areas)
      - Style counter (how well your style counters the opponent's)
      - Player suitability (how well players fit their assigned roles)
    """

    def score(
        self,
        own_tactics: Dict,
        opponent_tactics: Dict,
        own_players: List[Dict],
        opponent_players: List[Dict],
    ) -> float:
        """Return a tactical effectiveness score from 0 to 100.

        Parameters
        ----------
        own_tactics : dict
            Keys may include 'style', 'formation', 'mentality', 'zones'.
            'zones' is a dict mapping zone names to player counts.
        opponent_tactics : dict
            Same structure as own_tactics.
        own_players : list[dict]
            Each dict should have 'position'/'role' and attribute keys
            (e.g. 'pace', 'shooting', 'defending', etc.).
        opponent_players : list[dict]
            Same structure as own_players.
        """
        overload = self.zone_overload_score(own_tactics, opponent_tactics)
        style = self.style_counter_score(own_tactics, opponent_tactics)
        suitability = self.player_suitability_score(own_players, own_tactics)

        # Each component is 0-100; weight equally at 33.33% each
        total = (overload + style + suitability) / 3.0
        return max(0.0, min(100.0, total))

    # ------------------------------------------------------------------
    # Component 1: Zone overload
    # ------------------------------------------------------------------
    def zone_overload_score(
        self, own_tactics: Dict, opponent_tactics: Dict
    ) -> float:
        """Score based on numerical advantages in each zone.

        A 3v2 overload in a zone earns a significant bonus.
        Returns 0-100.
        """
        own_zones = self._get_zone_counts(own_tactics)
        opp_zones = self._get_zone_counts(opponent_tactics)

        score = 50.0  # Start at neutral

        for zone in _ZONES:
            own_count = own_zones.get(zone, 0)
            opp_count = opp_zones.get(zone, 0)
            diff = own_count - opp_count

            if diff >= 2:
                # Strong overload (e.g. 3v1, 4v2)
                score += 12.0
            elif diff == 1:
                # Slight numerical advantage
                score += 6.0
            elif diff == -1:
                score -= 4.0
            elif diff <= -2:
                score -= 8.0

        return max(0.0, min(100.0, score))

    # ------------------------------------------------------------------
    # Component 2: Style counter
    # ------------------------------------------------------------------
    def style_counter_score(
        self, own_tactics: Dict, opponent_tactics: Dict
    ) -> float:
        """Score how well own style counters the opponent's.

        Returns 0-100.
        """
        own_style = own_tactics.get("style", "balanced")
        opp_style = opponent_tactics.get("style", "balanced")

        counters = _STYLE_COUNTERS.get(own_style, _STYLE_COUNTERS["balanced"])
        advantage = counters.get(opp_style, 0.0)

        # Map advantage (-15..+15 range) to 0-100 scale
        # 0 advantage -> 50, +15 -> ~85, -15 -> ~15
        score = 50.0 + advantage * (35.0 / 15.0)

        # Factor in mentality alignment
        own_mentality = own_tactics.get("mentality", "balanced")
        if own_mentality == "attacking" and own_style in ("high_press", "possession"):
            score += 5.0
        elif own_mentality == "defensive" and own_style in ("counter_attack", "long_ball"):
            score += 5.0
        elif own_mentality == "ultra_defensive" and own_style == "counter_attack":
            score += 3.0

        return max(0.0, min(100.0, score))

    # ------------------------------------------------------------------
    # Component 3: Player suitability
    # ------------------------------------------------------------------
    def player_suitability_score(
        self, players: List[Dict], tactics: Dict
    ) -> float:
        """Score how well players fit their assigned roles.

        Each player is evaluated on how their attributes match the
        key attributes for their position/role. Returns 0-100.
        """
        if not players:
            return 50.0

        total = 0.0
        count = 0

        for player in players:
            role = player.get("role") or player.get("position", "CM")
            role = role.upper().strip()
            key_attrs = _ROLE_ATTRIBUTES.get(role, _ROLE_ATTRIBUTES.get("CM", []))

            attr_sum = 0.0
            attr_count = 0
            for attr in key_attrs:
                val = player.get(attr)
                if val is not None:
                    attr_sum += float(val)
                    attr_count += 1

            if attr_count > 0:
                # Average attribute value (expected range 1-99)
                avg = attr_sum / attr_count
                # Map 1-99 to roughly 0-100 suitability
                total += avg
                count += 1

        if count == 0:
            return 50.0

        return max(0.0, min(100.0, total / count))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _get_zone_counts(tactics: Dict) -> dict[str, int]:
        """Extract zone player counts from tactics dict.

        If 'zones' key is present, use it directly.
        Otherwise, estimate from formation string (e.g. '4-3-3').
        """
        if "zones" in tactics:
            return tactics["zones"]

        formation = tactics.get("formation", "4-4-2")
        parts = str(formation).split("-")
        try:
            nums = [int(p) for p in parts]
        except (ValueError, TypeError):
            nums = [4, 4, 2]

        zones: dict[str, int] = {}
        if len(nums) >= 3:
            zones["defence"] = nums[0]
            zones["midfield"] = nums[1] if len(nums) == 3 else nums[1] + nums[2]
            zones["attack"] = nums[-1]
        elif len(nums) == 2:
            zones["defence"] = nums[0]
            zones["attack"] = nums[1]
        else:
            zones["defence"] = 4
            zones["midfield"] = 4
            zones["attack"] = 2

        # Estimate flanks from formation width
        def_count = zones.get("defence", 4)
        zones["left_flank"] = 1 if def_count >= 4 else 0
        zones["right_flank"] = 1 if def_count >= 4 else 0

        return zones
