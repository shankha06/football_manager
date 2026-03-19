"""Tactical system: formations, player roles, and tactical instructions.

Each formation maps 10 outfield slots to (zone_col, zone_row) pairs for
both defending and attacking phases.  Tactical instructions modify how
the match engine resolves events (e.g. short-passing bonus, pressing
intensity).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from fm.engine.pitch import ZoneCol, ZoneRow


# ── Formation definitions ──────────────────────────────────────────────────
# Each formation is a dict mapping slot index (0-9, outfield) to
# (defending_zone, attacking_zone) as (col, row) tuples.
# The GK always occupies (0, 1).
#
# Slot ordering convention: defenders L→R, midfielders L→R, forwards L→R.

FORMATIONS: dict[str, dict[str, list[tuple[int, int]]]] = {
    "4-4-2": {
        "defend": [
            (1, 0), (1, 1), (1, 1), (1, 2),   # LB, CB, CB, RB
            (2, 0), (2, 1), (2, 1), (2, 2),   # LM, CM, CM, RM
            (4, 0), (4, 2),                     # ST, ST
        ],
        "attack": [
            (2, 0), (1, 1), (1, 1), (2, 2),
            (3, 0), (3, 1), (3, 1), (3, 2),
            (5, 0), (5, 2),
        ],
    },
    "4-3-3": {
        "defend": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 2),
            (4, 0), (4, 1), (4, 2),
        ],
        "attack": [
            (2, 0), (1, 1), (1, 1), (2, 2),
            (3, 0), (3, 1), (3, 2),
            (5, 0), (5, 1), (5, 2),
        ],
    },
    "4-2-3-1": {
        "defend": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 1), (2, 1),
            (3, 0), (3, 1), (3, 2),
            (4, 1),
        ],
        "attack": [
            (2, 0), (1, 1), (1, 1), (2, 2),
            (2, 1), (3, 1),
            (4, 0), (4, 1), (4, 2),
            (5, 1),
        ],
    },
    "3-5-2": {
        "defend": [
            (1, 0), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 1), (2, 1), (2, 2),
            (4, 0), (4, 2),
        ],
        "attack": [
            (1, 0), (1, 1), (1, 2),
            (3, 0), (3, 1), (2, 1), (3, 1), (3, 2),
            (5, 0), (5, 2),
        ],
    },
    "5-3-2": {
        "defend": [
            (1, 0), (1, 0), (1, 1), (1, 2), (1, 2),
            (2, 0), (2, 1), (2, 2),
            (4, 0), (4, 2),
        ],
        "attack": [
            (2, 0), (1, 0), (1, 1), (1, 2), (2, 2),
            (3, 0), (3, 1), (3, 2),
            (5, 0), (5, 2),
        ],
    },
    "4-1-4-1": {
        "defend": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 1),
            (3, 0), (3, 1), (3, 1), (3, 2),
            (4, 1),
        ],
        "attack": [
            (2, 0), (1, 1), (1, 1), (2, 2),
            (2, 1),
            (4, 0), (3, 1), (3, 1), (4, 2),
            (5, 1),
        ],
    },
    "3-4-3": {
        "defend": [
            (1, 0), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 1), (2, 2),
            (4, 0), (4, 1), (4, 2),
        ],
        "attack": [
            (1, 0), (1, 1), (1, 2),
            (3, 0), (3, 1), (3, 1), (3, 2),
            (5, 0), (5, 1), (5, 2),
        ],
    },
    "4-5-1": {
        "defend": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 1), (2, 1), (2, 2),
            (4, 1),
        ],
        "attack": [
            (2, 0), (1, 1), (1, 1), (2, 2),
            (3, 0), (3, 1), (3, 1), (3, 1), (3, 2),
            (5, 1),
        ],
    },
}


# ── Tactical modifiers ─────────────────────────────────────────────────────

MENTALITY_RISK: dict[str, float] = {
    "very_defensive": -0.25,
    "defensive":      -0.15,
    "cautious":       -0.05,
    "balanced":        0.00,
    "positive":        0.10,
    "attacking":       0.20,
    "very_attacking":  0.30,
}

TEMPO_MODIFIER: dict[str, float] = {
    "very_slow": -0.20,
    "slow":      -0.10,
    "normal":     0.00,
    "fast":       0.10,
    "very_fast":  0.20,
}

PRESSING_MODIFIER: dict[str, float] = {
    "low":       -0.15,
    "standard":   0.00,
    "high":       0.15,
    "very_high":  0.25,
}

PASSING_STYLE_MODIFIER: dict[str, float] = {
    "very_short":  0.15,   # positive = easier short passes
    "short":       0.08,
    "mixed":       0.00,
    "direct":     -0.05,
    "very_direct": -0.12,
}

WIDTH_MODIFIER: dict[str, float] = {
    "very_narrow": -0.15,
    "narrow":      -0.08,
    "normal":       0.00,
    "wide":         0.08,
    "very_wide":    0.15,
}


@dataclass
class TacticalContext:
    """Resolved tactical modifiers for one side during a match."""
    formation: str = "4-4-2"
    mentality: str = "balanced"
    tempo: str = "normal"
    pressing: str = "standard"
    passing_style: str = "mixed"
    width: str = "normal"
    defensive_line: str = "normal"

    # Role assignments for the 10 outfield slots (indices 0-9)
    roles: list[str] = field(default_factory=lambda: ["CB"] * 4 + ["CM"] * 4 + ["ST"] * 2)

    # Advanced options (stored in TacticalSetup but now used by engine)
    offside_trap: bool = False
    counter_attack: bool = False
    play_out_from_back: bool = False
    time_wasting: str = "off"

    # In-match plan adjustments
    match_plan_winning: str = "hold_lead"
    match_plan_losing: str = "push_forward"
    match_plan_drawing: str = "stay_balanced"

    # ── Mid-match formation lock (prevents repeated switches) ──
    formation_locked: bool = False

    @property
    def risk_modifier(self) -> float:
        return MENTALITY_RISK.get(self.mentality, 0.0)

    @property
    def tempo_modifier(self) -> float:
        return TEMPO_MODIFIER.get(self.tempo, 0.0)

    @property
    def press_modifier(self) -> float:
        return PRESSING_MODIFIER.get(self.pressing, 0.0)

    @property
    def passing_modifier(self) -> float:
        return PASSING_STYLE_MODIFIER.get(self.passing_style, 0.0)

    @property
    def width_modifier(self) -> float:
        return WIDTH_MODIFIER.get(self.width, 0.0)

    def defending_zones(self) -> list[tuple[int, int]]:
        """Get the defensive zone assignments from the formation."""
        fm = FORMATIONS.get(self.formation, FORMATIONS["4-4-2"])
        return fm["defend"]

    def attacking_zones(self) -> list[tuple[int, int]]:
        fm = FORMATIONS.get(self.formation, FORMATIONS["4-4-2"])
        return fm["attack"]

    def transition_zones(self) -> list[tuple[int, int]]:
        """Get the transition zone assignments from the formation."""
        dual = DUAL_PHASE_FORMATIONS.get(self.formation)
        if dual:
            return dual["transition"]
        # Fallback: average of defend and attack (use defend as proxy)
        return self.defending_zones()

    @classmethod
    def from_db(cls, setup) -> TacticalContext:
        """Build from a TacticalSetup ORM object."""
        return cls(
            formation=setup.formation or "4-4-2",
            mentality=setup.mentality or "balanced",
            tempo=setup.tempo or "normal",
            pressing=setup.pressing or "standard",
            passing_style=setup.passing_style or "mixed",
            width=setup.width or "normal",
            defensive_line=setup.defensive_line or "normal",
            offside_trap=getattr(setup, "offside_trap", False) or False,
            counter_attack=getattr(setup, "counter_attack", False) or False,
            play_out_from_back=getattr(setup, "play_out_from_back", False) or False,
            time_wasting=getattr(setup, "time_wasting", "off") or "off",
            match_plan_winning=getattr(setup, "match_plan_winning", "hold_lead") or "hold_lead",
            match_plan_losing=getattr(setup, "match_plan_losing", "push_forward") or "push_forward",
            match_plan_drawing=getattr(setup, "match_plan_drawing", "stay_balanced") or "stay_balanced",
        )


# ── Dual-phase formations (in_possession / out_of_possession / transition) ──
# Transition zones represent the compact shape a team takes when the ball
# is in flux (turnovers, loose balls, restarts).

DUAL_PHASE_FORMATIONS: dict[str, dict[str, list[tuple[int, int]]]] = {
    "4-4-2": {
        "in_possession": FORMATIONS["4-4-2"]["attack"],
        "out_of_possession": FORMATIONS["4-4-2"]["defend"],
        "transition": [
            (1, 0), (1, 1), (1, 1), (1, 2),   # defence holds
            (2, 0), (2, 1), (2, 1), (2, 2),   # midfield compact
            (3, 0), (3, 2),                     # strikers press high
        ],
    },
    "4-3-3": {
        "in_possession": FORMATIONS["4-3-3"]["attack"],
        "out_of_possession": FORMATIONS["4-3-3"]["defend"],
        "transition": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 2),
            (3, 0), (3, 1), (3, 2),
        ],
    },
    "4-2-3-1": {
        "in_possession": FORMATIONS["4-2-3-1"]["attack"],
        "out_of_possession": FORMATIONS["4-2-3-1"]["defend"],
        "transition": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 1), (2, 1),
            (3, 0), (3, 1), (3, 2),
            (3, 1),
        ],
    },
    "3-5-2": {
        "in_possession": FORMATIONS["3-5-2"]["attack"],
        "out_of_possession": FORMATIONS["3-5-2"]["defend"],
        "transition": [
            (1, 0), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 1), (2, 1), (2, 2),
            (3, 0), (3, 2),
        ],
    },
    "5-3-2": {
        "in_possession": FORMATIONS["5-3-2"]["attack"],
        "out_of_possession": FORMATIONS["5-3-2"]["defend"],
        "transition": [
            (1, 0), (1, 0), (1, 1), (1, 2), (1, 2),
            (2, 0), (2, 1), (2, 2),
            (3, 0), (3, 2),
        ],
    },
    "4-1-4-1": {
        "in_possession": FORMATIONS["4-1-4-1"]["attack"],
        "out_of_possession": FORMATIONS["4-1-4-1"]["defend"],
        "transition": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 1),
            (2, 0), (2, 1), (2, 1), (2, 2),
            (3, 1),
        ],
    },
    "3-4-3": {
        "in_possession": FORMATIONS["3-4-3"]["attack"],
        "out_of_possession": FORMATIONS["3-4-3"]["defend"],
        "transition": [
            (1, 0), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 1), (2, 2),
            (3, 0), (3, 1), (3, 2),
        ],
    },
    "4-5-1": {
        "in_possession": FORMATIONS["4-5-1"]["attack"],
        "out_of_possession": FORMATIONS["4-5-1"]["defend"],
        "transition": [
            (1, 0), (1, 1), (1, 1), (1, 2),
            (2, 0), (2, 1), (2, 1), (2, 1), (2, 2),
            (3, 1),
        ],
    },
}

# Also add transition zones to the original FORMATIONS dict
for _name, _dual in DUAL_PHASE_FORMATIONS.items():
    if _name in FORMATIONS:
        FORMATIONS[_name]["transition"] = _dual["transition"]


def compute_zone_overloads(
    home_formation: str, away_formation: str,
) -> dict[tuple[int, int], tuple[int, int]]:
    """Compare player counts per zone between two formations.

    Uses defending zones for both sides (as a proxy for shape).
    The away zones are mirrored (col 5-col) so both teams share
    the same coordinate system.

    Returns:
        Dict mapping ``(col, row)`` to ``(home_count, away_count)``
        for zones where one side has a numerical advantage (>= 2 more).
    """
    home_fm = FORMATIONS.get(home_formation, FORMATIONS["4-4-2"])
    away_fm = FORMATIONS.get(away_formation, FORMATIONS["4-4-2"])

    home_defend = home_fm["defend"]
    away_defend = away_fm["defend"]

    # Count players per zone for home
    home_counts: dict[tuple[int, int], int] = {}
    for col, row in home_defend:
        home_counts[(col, row)] = home_counts.get((col, row), 0) + 1

    # Count for away (mirror columns: away col 1 maps to home col 4, etc.)
    away_counts: dict[tuple[int, int], int] = {}
    for col, row in away_defend:
        mirrored_col = 5 - col
        away_counts[(mirrored_col, row)] = away_counts.get((mirrored_col, row), 0) + 1

    # Find overloads
    all_zones = set(home_counts.keys()) | set(away_counts.keys())
    overloads: dict[tuple[int, int], tuple[int, int]] = {}
    for zone in all_zones:
        hc = home_counts.get(zone, 0)
        ac = away_counts.get(zone, 0)
        if abs(hc - ac) >= 2:
            overloads[zone] = (hc, ac)

    return overloads
