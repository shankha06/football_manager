"""Pre-match context: aggregates every environmental and team factor that
should influence a match result beyond raw player attributes.

The MatchContext is built before each match and fed into the simulator so
that morale, form, weather, tactical matchups, crowd atmosphere, fatigue,
and home advantage all contribute to the final outcome.
"""
from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from fm.db.models import Club, Season, Player
    from fm.engine.tactics import TacticalContext


# ── Weather & pitch enums ─────────────────────────────────────────────────

class Weather(str, enum.Enum):
    CLEAR = "clear"
    RAIN = "rain"
    HEAVY_RAIN = "heavy_rain"
    SNOW = "snow"
    WIND = "wind"
    HOT = "hot"
    COLD = "cold"


class PitchCondition(str, enum.Enum):
    PERFECT = "perfect"
    GOOD = "good"
    WORN = "worn"
    HEAVY = "heavy"
    FROZEN = "frozen"


# ── Tactical Matchup (granular advantages used by V2 engine) ──────────────

@dataclass
class TacticalMatchup:
    """Granular tactical advantages/disadvantages between two sides.

    Each field ranges roughly [-0.25, +0.25].  Positive = home advantage.
    The V2 engine reads these to alter turnover rates, chain progression,
    shot creation, counter-attack frequency, and set-piece danger.
    """
    # Pressing interaction: positive = home's press is more effective
    pressing_advantage: float = 0.0

    # Counter-attack vulnerability: positive = home can counter better
    counter_vulnerability: float = 0.0

    # Width exploitation: positive = home exploits opponent's flanks
    width_exploitation: float = 0.0

    # Midfield control: positive = home dominates midfield
    midfield_control: float = 0.0

    # Defensive solidity bonus: positive = home harder to break down
    defensive_solidity: float = 0.0

    # Creative advantage: positive = home creates better chances
    creative_advantage: float = 0.0

    # Aerial/set-piece threat advantage
    aerial_advantage: float = 0.0

    # Overall tactical edge (sum of above, clamped)
    @property
    def home_total(self) -> float:
        return max(-0.25, min(0.25, (
            self.pressing_advantage * 0.20
            + self.counter_vulnerability * 0.20
            + self.width_exploitation * 0.15
            + self.midfield_control * 0.20
            + self.defensive_solidity * 0.10
            + self.creative_advantage * 0.10
            + self.aerial_advantage * 0.05
        )))

    @property
    def away_total(self) -> float:
        return -self.home_total

    def for_side(self, side: str) -> dict[str, float]:
        """Get advantages from perspective of a side.

        Returns dict of modifier names → values where positive = good for that side.
        """
        sign = 1.0 if side == "home" else -1.0
        return {
            "pressing": self.pressing_advantage * sign,
            "counter": self.counter_vulnerability * sign,
            "width": self.width_exploitation * sign,
            "midfield": self.midfield_control * sign,
            "defensive": self.defensive_solidity * sign,
            "creative": self.creative_advantage * sign,
            "aerial": self.aerial_advantage * sign,
        }


# ── Weather commentary templates ──────────────────────────────────────────

_WEATHER_COMMENTARY = {
    Weather.CLEAR: [
        "Perfect conditions for football today.",
        "A beautiful day for a match — clear skies overhead.",
    ],
    Weather.RAIN: [
        "🌧️ Light rain falling — the surface will be slippery.",
        "🌧️ Wet conditions today, could see some errors.",
    ],
    Weather.HEAVY_RAIN: [
        "🌧️ Heavy rain pouring down — this will be a battle!",
        "🌧️ Torrential conditions! The pitch is waterlogged in places.",
    ],
    Weather.SNOW: [
        "❄️ Snow falling! Tricky conditions on a white pitch.",
        "❄️ Winter wonderland out there — visibility will be poor.",
    ],
    Weather.WIND: [
        "💨 Strong wind swirling — long balls will drift.",
        "💨 Gusty conditions today, crossing and shooting will be affected.",
    ],
    Weather.HOT: [
        "☀️ Sweltering heat — stamina will be tested today.",
        "☀️ It's a scorcher! Players will need to manage their energy.",
    ],
    Weather.COLD: [
        "🥶 Bitterly cold today — the pitch is firm.",
        "🥶 Freezing conditions, players will need to stay warm.",
    ],
}

_PITCH_COMMENTARY = {
    PitchCondition.HEAVY: "The pitch is heavy and cutting up — dribbling will be tough.",
    PitchCondition.FROZEN: "The surface is frozen solid — players need to watch their footing.",
    PitchCondition.WORN: "The pitch is patchy and worn — expect some bobbles.",
}


# ── MatchContext ──────────────────────────────────────────────────────────

@dataclass
class MatchContext:
    """All pre-match factors that modify a simulation."""

    # Home advantage
    home_advantage: float = 0.06

    # Morale modifiers (converted from 0-100 scale to -0.10..+0.10)
    home_morale_mod: float = 0.0
    away_morale_mod: float = 0.0

    # Form modifiers (from recent W/D/L string)
    home_form_mod: float = 0.0
    away_form_mod: float = 0.0

    # Training sharpness (0.0-1.0; match_prep → highest)
    home_sharpness: float = 0.80
    away_sharpness: float = 0.80

    # Team cohesion (higher rep = more settled squad)
    home_cohesion_mod: float = 0.0
    away_cohesion_mod: float = 0.0

    # Influence-weighted morale (0-100) - used for systemic performance sabotage
    home_influence_morale: float = 65.0
    away_influence_morale: float = 65.0

    # Weather & pitch
    weather: Weather = Weather.CLEAR
    pitch_condition: PitchCondition = PitchCondition.GOOD

    # Context flags
    is_derby: bool = False
    is_cup: bool = False
    is_cup_final: bool = False
    importance: float = 1.0

    # Tactical advantage from matchup analysis (legacy flat values)
    tactical_advantage_home: float = 0.0
    tactical_advantage_away: float = 0.0

    # Granular tactical matchup (used by V2 engine)
    tactical_matchup: TacticalMatchup | None = None

    # Crowd factor (attendance / capacity)
    crowd_factor: float = 0.85

    # Fatigue from fixture congestion (1.0 = fresh, 0.7 = congested)
    fatigue_home: float = 1.0
    fatigue_away: float = 1.0

    # List of (p1_id, p2_id, type, strength) from PlayerRelationship
    player_relationships: list[tuple[int, int, str, float]] = field(default_factory=list)

    # DB session and season info for MatchSituationEngine
    session: Session | None = None
    season_year: int = 2024
    matchday: int = 1

    # ── Derived modifiers ─────────────────────────────────────────────

    def home_modifier(self) -> float:
        """Combined modifier for home team (roughly -0.3 to +0.3)."""
        return (
            self.home_advantage
            + self.home_morale_mod
            + self.home_form_mod
            + self.tactical_advantage_home
            + self.home_cohesion_mod
            + (self.crowd_factor - 0.5) * 0.04  # loud crowd helps
        )

    def away_modifier(self) -> float:
        return (
            self.away_morale_mod
            + self.away_form_mod
            + self.tactical_advantage_away
            + self.away_cohesion_mod
        )

    def performance_sabotage_penalty(self, side: str) -> float:
        """Penalty applied to vision/composure when locker room is mutinous.
        
        If influence_morale < 40, returns a penalty (0.0 to 0.15).
        """
        morale = self.home_influence_morale if side == "home" else self.away_influence_morale
        if morale >= 40:
            return 0.0
        
        # Linear penalty from 40 (0.0) down to 10 (0.15)
        raw_penalty = (40.0 - morale) / 30.0 * 0.15
        return min(0.15, raw_penalty)

    def weather_passing_penalty(self) -> float:
        """How much weather degrades passing (0.0 = no effect)."""
        return {
            Weather.CLEAR: 0.0,
            Weather.RAIN: 0.04,
            Weather.HEAVY_RAIN: 0.10,
            Weather.SNOW: 0.08,
            Weather.WIND: 0.03,
            Weather.HOT: 0.01,
            Weather.COLD: 0.02,
        }.get(self.weather, 0.0)

    def weather_pace_penalty(self) -> float:
        return {
            Weather.CLEAR: 0.0,
            Weather.RAIN: 0.02,
            Weather.HEAVY_RAIN: 0.06,
            Weather.SNOW: 0.08,
            Weather.WIND: 0.01,
            Weather.HOT: 0.04,
            Weather.COLD: 0.02,
        }.get(self.weather, 0.0)

    def weather_shooting_mod(self) -> float:
        """Positive = helps shooting, negative = hurts."""
        return {
            Weather.CLEAR: 0.0,
            Weather.RAIN: -0.02,
            Weather.HEAVY_RAIN: -0.05,
            Weather.SNOW: -0.04,
            Weather.WIND: -0.06,
            Weather.HOT: 0.0,
            Weather.COLD: -0.01,
        }.get(self.weather, 0.0)

    def pitch_dribble_penalty(self) -> float:
        return {
            PitchCondition.PERFECT: 0.0,
            PitchCondition.GOOD: 0.0,
            PitchCondition.WORN: 0.03,
            PitchCondition.HEAVY: 0.08,
            PitchCondition.FROZEN: 0.06,
        }.get(self.pitch_condition, 0.0)

    def weather_fatigue_multiplier(self) -> float:
        """Extra fatigue drain from weather (1.0 = normal)."""
        return {
            Weather.CLEAR: 1.0,
            Weather.RAIN: 1.10,
            Weather.HEAVY_RAIN: 1.20,
            Weather.SNOW: 1.15,
            Weather.WIND: 1.05,
            Weather.HOT: 1.35,
            Weather.COLD: 1.05,
        }.get(self.weather, 1.0)

    def kickoff_commentary(self) -> list[str]:
        """Commentary lines for match start conditions."""
        lines = []
        templates = _WEATHER_COMMENTARY.get(self.weather, [])
        if templates:
            lines.append(random.choice(templates))
        pitch_line = _PITCH_COMMENTARY.get(self.pitch_condition)
        if pitch_line:
            lines.append(pitch_line)
        return lines


# ── Tactical matchup analysis ────────────────────────────────────────────

def _get_style_tags(tac: TacticalContext) -> set[str]:
    """Map a TacticalContext to tactical style tags."""
    tags: set[str] = set()

    # Pressing
    if tac.pressing in ("high", "very_high"):
        tags.add("high_press")
    elif tac.pressing == "low":
        tags.add("low_press")

    # Passing style
    if tac.passing_style in ("short", "very_short"):
        tags.add("slow_possession")
        tags.add("short_passing")
    elif tac.passing_style in ("direct", "very_direct"):
        tags.add("direct")

    # Mentality
    if tac.mentality in ("attacking", "very_attacking"):
        tags.add("attacking")
    elif tac.mentality in ("defensive", "very_defensive"):
        tags.add("defensive")

    # Width
    if tac.width in ("wide", "very_wide"):
        tags.update({"wide_play", "wide"})
    elif tac.width in ("narrow", "very_narrow"):
        tags.update({"narrow_play", "narrow"})

    # Defensive line
    if tac.defensive_line == "high":
        tags.add("high_line")
    elif tac.defensive_line == "deep":
        tags.add("deep_block")

    # Compound styles
    if tac.tempo in ("slow", "very_slow") and "short_passing" in tags:
        tags.add("possession")
    if tac.tempo in ("fast", "very_fast") and tac.mentality in (
        "cautious", "defensive", "very_defensive",
    ):
        tags.add("counter")

    return tags


# Style interaction table: (attacker_tag, defender_tag) → attacker bonus
_STYLE_COUNTERS: dict[tuple[str, str], float] = {
    ("high_press", "slow_possession"): 0.08,
    ("high_press", "possession"): 0.06,
    ("high_press", "direct"): -0.05,
    ("direct", "high_press"): 0.05,
    ("counter", "high_line"): 0.10,
    ("counter", "deep_block"): -0.05,
    ("possession", "low_press"): 0.06,
    ("possession", "high_press"): -0.04,
    ("wide_play", "narrow"): 0.07,
    ("wide_play", "narrow_play"): 0.07,
    ("narrow_play", "wide"): -0.04,
    ("attacking", "defensive"): 0.03,
    ("defensive", "attacking"): 0.02,
    ("deep_block", "possession"): 0.03,
    ("high_line", "counter"): -0.08,
    ("low_press", "direct"): -0.04,
}

# Formation strength/weakness system
_FORMATION_STRENGTHS: dict[str, set[str]] = {
    "4-4-2": {"defensive_solidity", "direct_play", "crossing"},
    "4-3-3": {"wing_play", "pressing", "width"},
    "4-2-3-1": {"creative_midfield", "defensive_cover", "flexibility"},
    "3-5-2": {"midfield_control", "wing_back_overload", "central_play"},
    "5-3-2": {"defensive_solidity", "counter_attack", "compactness"},
    "4-1-4-1": {"midfield_screen", "defensive_cover", "balance"},
    "3-4-3": {"attacking_width", "numerical_advantage_attack", "pressing"},
    "4-5-1": {"midfield_control", "compactness", "defensive_solidity"},
}

_FORMATION_WEAKNESSES: dict[str, set[str]] = {
    "4-4-2": {"midfield_overrun", "limited_creativity"},
    "4-3-3": {"defensive_vulnerability", "wide_spaces"},
    "4-2-3-1": {"isolated_striker", "slow_buildup"},
    "3-5-2": {"wide_vulnerability", "wing_exposed"},
    "5-3-2": {"limited_width", "attacking_output"},
    "4-1-4-1": {"isolated_striker", "limited_width"},
    "3-4-3": {"defensive_vulnerability", "space_behind"},
    "4-5-1": {"isolated_striker", "limited_attacking"},
}

# Which strengths exploit which weaknesses
_STRENGTH_EXPLOITS_WEAKNESS = {
    "wing_play": "wide_vulnerability",
    "attacking_width": "wide_vulnerability",
    "width": "wide_vulnerability",
    "pressing": "slow_buildup",
    "midfield_control": "midfield_overrun",
    "creative_midfield": "limited_creativity",
    "counter_attack": "space_behind",
    "direct_play": "defensive_vulnerability",
    "crossing": "limited_width",
}


def analyze_tactical_matchup(
    home_tac: TacticalContext, away_tac: TacticalContext,
) -> tuple[float, float]:
    """Analyze tactical interaction. Returns (home_adv, away_adv) in [-0.15, 0.15].

    Also computes the granular TacticalMatchup available via
    analyze_tactical_matchup_detailed().
    """
    matchup = analyze_tactical_matchup_detailed(home_tac, away_tac)
    return matchup.home_total, matchup.away_total


def analyze_tactical_matchup_detailed(
    home_tac: TacticalContext, away_tac: TacticalContext,
) -> TacticalMatchup:
    """Compute granular tactical advantages between two setups.

    This is the core of the tactical rock-paper-scissors system.
    Each tactical dimension is evaluated independently so the match engine
    can apply effects precisely (e.g., pressing advantage → more turnovers,
    counter vulnerability → more through-balls).
    """
    h_tags = _get_style_tags(home_tac)
    a_tags = _get_style_tags(away_tac)

    m = TacticalMatchup()

    # ── 1. Pressing interaction ──────────────────────────────────────────
    # High press vs high line = devastating turnovers in dangerous zones
    # High press vs deep block = pressing is wasted, energy drain
    # High press vs direct play = bypassed easily
    # High press vs short passing = interception opportunities
    h_press = _press_level(home_tac.pressing)
    a_press = _press_level(away_tac.pressing)

    # Home pressing effectiveness vs away buildup style
    h_press_eff = 0.0
    if h_press >= 2:  # high or very_high
        if "high_line" in a_tags:
            h_press_eff += 0.15  # pressing a high line = turnovers near their goal
        if "short_passing" in a_tags or "slow_possession" in a_tags:
            h_press_eff += 0.10  # pressing short passing = interceptions
        if "deep_block" in a_tags:
            h_press_eff -= 0.10  # nothing to press if they sit deep
        if "direct" in a_tags:
            h_press_eff -= 0.08  # long balls bypass press
        if home_tac.defensive_line == "high":
            h_press_eff += 0.05  # coordinated press
    elif h_press <= -1:
        if "possession" in a_tags:
            h_press_eff -= 0.08  # low press lets possession team dominate

    a_press_eff = 0.0
    if a_press >= 2:
        if "high_line" in h_tags:
            a_press_eff += 0.15
        if "short_passing" in h_tags or "slow_possession" in h_tags:
            a_press_eff += 0.10
        if "deep_block" in h_tags:
            a_press_eff -= 0.10
        if "direct" in h_tags:
            a_press_eff -= 0.08
        if away_tac.defensive_line == "high":
            a_press_eff += 0.05
    elif a_press <= -1:
        if "possession" in h_tags:
            a_press_eff -= 0.08

    m.pressing_advantage = max(-0.25, min(0.25, h_press_eff - a_press_eff))

    # ── 2. Counter-attack vulnerability ──────────────────────────────────
    # Counter style vs attacking mentality + high line = lethal
    # Counter style vs deep block = neutralized
    h_counter = 0.0
    a_counter = 0.0

    if "counter" in h_tags or home_tac.counter_attack:
        if "attacking" in a_tags and "high_line" in a_tags:
            h_counter += 0.20  # the dream scenario for counter-attacking
        elif "attacking" in a_tags:
            h_counter += 0.12
        elif "high_line" in a_tags:
            h_counter += 0.10
        if "deep_block" in a_tags or "defensive" in a_tags:
            h_counter -= 0.08  # nothing to counter

    if "counter" in a_tags or away_tac.counter_attack:
        if "attacking" in h_tags and "high_line" in h_tags:
            a_counter += 0.20
        elif "attacking" in h_tags:
            a_counter += 0.12
        elif "high_line" in h_tags:
            a_counter += 0.10
        if "deep_block" in h_tags or "defensive" in h_tags:
            a_counter -= 0.08

    m.counter_vulnerability = max(-0.25, min(0.25, h_counter - a_counter))

    # ── 3. Width exploitation ────────────────────────────────────────────
    # Wide play vs narrow defending = overloads on flanks
    # Narrow play vs wide defending = central overload
    h_width = 0.0
    a_width = 0.0

    if "wide_play" in h_tags or "wide" in h_tags:
        if "narrow" in a_tags or "narrow_play" in a_tags:
            h_width += 0.15  # wide vs narrow = flanks exposed
        # 3-back formations struggle against width
        if away_tac.formation.startswith("3-"):
            h_width += 0.08

    if "narrow_play" in h_tags or "narrow" in h_tags:
        if "wide" in a_tags:
            h_width -= 0.05  # narrow teams concede width

    if "wide_play" in a_tags or "wide" in a_tags:
        if "narrow" in h_tags or "narrow_play" in h_tags:
            a_width += 0.15
        if home_tac.formation.startswith("3-"):
            a_width += 0.08

    if "narrow_play" in a_tags or "narrow" in a_tags:
        if "wide" in h_tags:
            a_width -= 0.05

    m.width_exploitation = max(-0.25, min(0.25, h_width - a_width))

    # ── 4. Midfield control ──────────────────────────────────────────────
    # Numerical advantage in midfield + possession style = domination
    h_mid = sum(1 for c, _ in home_tac.defending_zones() if 2 <= c <= 3)
    a_mid = sum(1 for c, _ in away_tac.defending_zones() if 2 <= c <= 3)

    mid_diff = h_mid - a_mid
    h_mid_ctrl = mid_diff * 0.04  # +0.04 per extra midfielder

    # Possession style amplifies midfield advantage
    if "possession" in h_tags or "slow_possession" in h_tags:
        h_mid_ctrl += 0.05
    if "possession" in a_tags or "slow_possession" in a_tags:
        h_mid_ctrl -= 0.05

    # Direct play bypasses midfield entirely
    if "direct" in h_tags:
        h_mid_ctrl -= 0.03  # doesn't matter if you skip midfield
    if "direct" in a_tags:
        h_mid_ctrl += 0.03  # opponent skipping = your midfield free

    m.midfield_control = max(-0.25, min(0.25, h_mid_ctrl))

    # ── 5. Defensive solidity ────────────────────────────────────────────
    # Deep block + low press + narrow = fortress
    # Parking the bus vs pure possession = effective (but boring)
    h_def = 0.0
    a_def = 0.0

    if "deep_block" in h_tags:
        h_def += 0.10
        if "defensive" in h_tags:
            h_def += 0.08  # full park-the-bus
        if "narrow" in h_tags:
            h_def += 0.05  # compact block

    if home_tac.offside_trap and "high_line" in h_tags:
        # Offside trap: risky but reduces space
        h_def += 0.04

    if "deep_block" in a_tags:
        a_def += 0.10
        if "defensive" in a_tags:
            a_def += 0.08
        if "narrow" in a_tags:
            a_def += 0.05

    if away_tac.offside_trap and "high_line" in a_tags:
        a_def += 0.04

    # Formation defensive strength
    h_def_slots = sum(1 for c, _ in home_tac.defending_zones() if c <= 1)
    a_def_slots = sum(1 for c, _ in away_tac.defending_zones() if c <= 1)
    h_def += (h_def_slots - 4) * 0.02  # bonus for 5-back, penalty for 3-back
    a_def += (a_def_slots - 4) * 0.02

    m.defensive_solidity = max(-0.25, min(0.25, h_def - a_def))

    # ── 6. Creative advantage ────────────────────────────────────────────
    # Play out from back + short passing vs high press = risky but creative
    # Direct play = fewer creative chances but harder to read
    h_creative = 0.0
    a_creative = 0.0

    if home_tac.play_out_from_back:
        h_creative += 0.06
        if a_press >= 2:
            h_creative -= 0.08  # risky vs high press
    if "short_passing" in h_tags:
        h_creative += 0.04

    if away_tac.play_out_from_back:
        a_creative += 0.06
        if h_press >= 2:
            a_creative -= 0.08
    if "short_passing" in a_tags:
        a_creative += 0.04

    # Formation creativity (CAM-heavy formations)
    h_att_slots = sum(1 for c, _ in home_tac.attacking_zones() if c >= 4)
    a_att_slots = sum(1 for c, _ in away_tac.attacking_zones() if c >= 4)
    h_creative += (h_att_slots - 3) * 0.02
    a_creative += (a_att_slots - 3) * 0.02

    m.creative_advantage = max(-0.25, min(0.25, h_creative - a_creative))

    # ── 7. Aerial / set piece ────────────────────────────────────────────
    # Direct + wide = more crosses = aerial threat matters more
    h_aerial = 0.0
    a_aerial = 0.0

    if "direct" in h_tags and ("wide" in h_tags or "wide_play" in h_tags):
        h_aerial += 0.10
    if "direct" in a_tags and ("wide" in a_tags or "wide_play" in a_tags):
        a_aerial += 0.10

    # 5-back with tall defenders = aerial fortress
    if h_def_slots >= 5:
        h_aerial += 0.05
    if a_def_slots >= 5:
        a_aerial += 0.05

    m.aerial_advantage = max(-0.25, min(0.25, h_aerial - a_aerial))

    # ── Formation strength/weakness interactions ─────────────────────────
    h_strengths = _FORMATION_STRENGTHS.get(home_tac.formation, set())
    a_strengths = _FORMATION_STRENGTHS.get(away_tac.formation, set())
    h_weaknesses = _FORMATION_WEAKNESSES.get(home_tac.formation, set())
    a_weaknesses = _FORMATION_WEAKNESSES.get(away_tac.formation, set())

    # Map exploits to the matchup dimensions they affect
    _EXPLOIT_TO_DIMENSION = {
        "wing_play": "width_exploitation",
        "attacking_width": "width_exploitation",
        "width": "width_exploitation",
        "pressing": "pressing_advantage",
        "midfield_control": "midfield_control",
        "creative_midfield": "creative_advantage",
        "counter_attack": "counter_vulnerability",
        "direct_play": "creative_advantage",
        "crossing": "aerial_advantage",
        "defensive_solidity": "defensive_solidity",
        "compactness": "defensive_solidity",
    }

    for strength in h_strengths:
        exploit = _STRENGTH_EXPLOITS_WEAKNESS.get(strength)
        if exploit and exploit in a_weaknesses:
            dim = _EXPLOIT_TO_DIMENSION.get(strength, None)
            if dim:
                current = getattr(m, dim)
                setattr(m, dim, max(-0.25, min(0.25, current + 0.04)))

    for strength in a_strengths:
        exploit = _STRENGTH_EXPLOITS_WEAKNESS.get(strength)
        if exploit and exploit in h_weaknesses:
            dim = _EXPLOIT_TO_DIMENSION.get(strength, None)
            if dim:
                current = getattr(m, dim)
                setattr(m, dim, max(-0.25, min(0.25, current - 0.04)))

    return m


def _press_level(pressing: str) -> int:
    """Convert pressing string to numeric level. higher = more aggressive."""
    return {"low": -1, "standard": 0, "high": 2, "very_high": 3}.get(pressing, 0)


# ── Build full context from DB ────────────────────────────────────────────

def _morale_to_mod(avg_morale: float) -> float:
    """Convert 0-100 morale average to -0.10..+0.10 modifier."""
    return max(-0.10, min(0.10, (avg_morale - 50.0) / 500.0))


def _form_string_to_mod(form_str: str) -> float:
    """Convert 'WWDLW' to a modifier roughly -0.08..+0.08."""
    if not form_str:
        return 0.0
    score = 0
    for ch in form_str[-5:]:
        if ch == "W":
            score += 3
        elif ch == "D":
            score += 1
        elif ch == "L":
            score -= 2
    return max(-0.08, min(0.08, score / 15.0 * 0.08))


def _sharpness_from_training(club) -> float:
    """Compute sharpness from training focus and squad fitness."""
    focus = getattr(club, "training_focus", "match_prep") or "match_prep"
    base = 0.90 if focus == "match_prep" else 0.70
    return min(1.0, base)


def _cohesion_from_reputation(rep: int) -> float:
    """Higher rep clubs tend to have better cohesion (simplified)."""
    return max(-0.05, min(0.05, (rep - 50) / 1000.0))


def _pick_weather() -> Weather:
    """Weighted random weather selection."""
    choices = [
        (Weather.CLEAR, 40),
        (Weather.RAIN, 20),
        (Weather.HEAVY_RAIN, 8),
        (Weather.WIND, 12),
        (Weather.COLD, 10),
        (Weather.HOT, 5),
        (Weather.SNOW, 5),
    ]
    weathers, weights = zip(*choices)
    return random.choices(weathers, weights=weights, k=1)[0]


def _pitch_from_weather(weather: Weather) -> PitchCondition:
    if weather == Weather.HEAVY_RAIN:
        return random.choice([PitchCondition.HEAVY, PitchCondition.WORN])
    if weather == Weather.SNOW:
        return random.choice([PitchCondition.FROZEN, PitchCondition.HEAVY])
    if weather == Weather.RAIN:
        return random.choice([PitchCondition.GOOD, PitchCondition.WORN])
    return random.choice([PitchCondition.PERFECT, PitchCondition.GOOD])


def build_match_context(
    session,
    home_club,
    away_club,
    home_tactics: TacticalContext | None = None,
    away_tactics: TacticalContext | None = None,
    season=None,
    is_cup: bool = False,
    matchday: int = 1,
) -> MatchContext:
    """Build a fully populated MatchContext from DB state."""
    from fm.db.models import Player, LeagueStanding

    ctx = MatchContext(
        session=session,
        season_year=season.year if season else 2024,
        matchday=matchday,
    )

    # Home advantage
    cap = home_club.stadium_capacity or 30000
    tier = 2
    if home_club.league_id:
        from fm.db.models import League
        league = session.get(League, home_club.league_id)
        if league:
            tier = league.tier
    ctx.home_advantage = 0.06
    if cap > 50000:
        ctx.home_advantage += 0.02
    if tier == 1:
        ctx.home_advantage += 0.02
    ctx.crowd_factor = random.uniform(0.70, 0.98)

    # Morale
    home_players = session.query(Player).filter_by(club_id=home_club.id).all()
    away_players = session.query(Player).filter_by(club_id=away_club.id).all()

    if home_players:
        avg_h_morale = sum(p.morale or 65.0 for p in home_players) / len(home_players)
        ctx.home_morale_mod = _morale_to_mod(avg_h_morale)
        
        # Extreme Realism: Influence-weighted morale
        from fm.world.dynamics import DynamicsManager, InfluenceLevel
        dm_h = DynamicsManager(session)
        h_hierarchy = dm_h.calculate_hierarchy(home_club.id)
        
        weighted_sum = 0.0
        total_weight = 0.0
        for p in home_players:
            level = h_hierarchy.get(p.id, InfluenceLevel.OTHER)
            weight = 1.0 if level == InfluenceLevel.TEAM_LEADER else (0.5 if level == InfluenceLevel.HIGHLY_INFLUENTIAL else 0.0)
            if weight > 0:
                weighted_sum += (p.morale or 65.0) * weight
                total_weight += weight
        ctx.home_influence_morale = weighted_sum / total_weight if total_weight > 0 else avg_h_morale

    if away_players:
        avg_a_morale = sum(p.morale or 65.0 for p in away_players) / len(away_players)
        ctx.away_morale_mod = _morale_to_mod(avg_a_morale)
        
        from fm.world.dynamics import DynamicsManager, InfluenceLevel
        dm_a = DynamicsManager(session)
        a_hierarchy = dm_a.calculate_hierarchy(away_club.id)
        
        weighted_sum = 0.0
        total_weight = 0.0
        for p in away_players:
            level = a_hierarchy.get(p.id, InfluenceLevel.OTHER)
            weight = 1.0 if level == InfluenceLevel.TEAM_LEADER else (0.5 if level == InfluenceLevel.HIGHLY_INFLUENTIAL else 0.0)
            if weight > 0:
                weighted_sum += (p.morale or 65.0) * weight
                total_weight += weight
        ctx.away_influence_morale = weighted_sum / total_weight if total_weight > 0 else avg_a_morale

    # Form from standings
    if season and home_club.league_id:
        h_st = session.query(LeagueStanding).filter_by(
            league_id=home_club.league_id, club_id=home_club.id,
            season=season.year,
        ).first()
        a_st = session.query(LeagueStanding).filter_by(
            league_id=away_club.league_id, club_id=away_club.id,
            season=season.year,
        ).first()
        if h_st:
            ctx.home_form_mod = _form_string_to_mod(h_st.form or "")
        if a_st:
            ctx.away_form_mod = _form_string_to_mod(a_st.form or "")

    # Sharpness from training
    ctx.home_sharpness = _sharpness_from_training(home_club)
    ctx.away_sharpness = _sharpness_from_training(away_club)

    # Cohesion
    ctx.home_cohesion_mod = _cohesion_from_reputation(home_club.reputation or 50)
    ctx.away_cohesion_mod = _cohesion_from_reputation(away_club.reputation or 50)

    # Weather & pitch
    ctx.weather = _pick_weather()
    ctx.pitch_condition = _pitch_from_weather(ctx.weather)

    # Cup flag
    ctx.is_cup = is_cup
    ctx.importance = 1.2 if is_cup else 1.0

    # Tactical matchup (both flat and granular)
    if home_tactics and away_tactics:
        matchup = analyze_tactical_matchup_detailed(home_tactics, away_tactics)
        ctx.tactical_matchup = matchup
        ctx.tactical_advantage_home = matchup.home_total
        ctx.tactical_advantage_away = matchup.away_total

    # Fetch relationships for context
    from fm.db.models import PlayerRelationship
    h_ids = [p.id for p in home_players]
    a_ids = [p.id for p in away_players]
    all_rel = session.query(PlayerRelationship).filter(
        (PlayerRelationship.player_a_id.in_(h_ids + a_ids)) |
        (PlayerRelationship.player_b_id.in_(h_ids + a_ids))
    ).all()
    for r in all_rel:
        ctx.player_relationships.append((
            r.player_a_id, r.player_b_id, r.relationship_type, r.strength or 50.0
        ))

    return ctx
