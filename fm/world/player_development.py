"""Realistic player development: attribute-specific growth curves, playing
time impact, injury effects, position-based overall calculation, and
retirement system.

Attribute growth timelines:
- Physical attributes (pace, acceleration, strength, stamina, jumping):
  Peak at 24-27, decline starts at 28, rapid decline after 32
- Technical attributes (finishing, passing, dribbling, ball_control):
  Peak at 25-30, slow decline after 31
- Mental attributes (composure, positioning, vision, reactions):
  Improve into early 30s, slow decline after 33

Playing time significantly impacts development for young players.
Injuries can permanently reduce potential and slow development.
"""
from __future__ import annotations

import math
import random
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from fm.db.models import Player, Club, PlayerStats, NewsItem


# ── Attribute Categories ───────────────────────────────────────────────────

_PHYSICAL_ATTRS = [
    "pace", "acceleration", "sprint_speed", "stamina", "strength",
    "jumping", "agility", "balance",
]

_TECHNICAL_ATTRS = [
    "shooting", "finishing", "shot_power", "long_shots", "volleys",
    "passing", "vision", "crossing", "short_passing", "long_passing",
    "curve", "dribbling", "ball_control", "free_kick_accuracy",
    "heading_accuracy", "penalties",
]

_DEFENSIVE_ATTRS = [
    "defending", "marking", "standing_tackle", "sliding_tackle", "interceptions",
]

_MENTAL_ATTRS = [
    "composure", "reactions", "positioning",
]

_GK_ATTRS = [
    "gk_diving", "gk_handling", "gk_kicking", "gk_positioning",
    "gk_reflexes", "gk_speed",
]

# Hidden / personality attributes that can change
_PERSONALITY_ATTRS = [
    "leadership", "teamwork", "determination", "ambition",
    "professionalism", "pressure_handling", "temperament",
]


# ── Growth Curve Functions ─────────────────────────────────────────────────

def _physical_growth_rate(age: int) -> float:
    """Physical attributes: peak 24-27, decline after 28.

    Returns a multiplier for attribute change probability.
    Positive = growth, negative = decline.
    """
    if age <= 17:
        return 1.8
    elif age <= 20:
        return 1.5
    elif age <= 23:
        return 1.0
    elif age <= 27:
        return 0.3        # maintenance / tiny gains
    elif age <= 29:
        return -0.3       # slight decline starts
    elif age <= 32:
        return -0.8       # noticeable decline
    elif age <= 35:
        return -1.5       # rapid decline
    else:
        return -2.5       # steep decline


def _technical_growth_rate(age: int) -> float:
    """Technical attributes: peak 25-30, slow decline after 31."""
    if age <= 17:
        return 1.5
    elif age <= 20:
        return 1.3
    elif age <= 24:
        return 1.0
    elif age <= 30:
        return 0.2        # maintenance
    elif age <= 33:
        return -0.3
    elif age <= 36:
        return -0.7
    else:
        return -1.2


def _mental_growth_rate(age: int) -> float:
    """Mental attributes: improve into early 30s, slow decline after 33."""
    if age <= 17:
        return 0.8
    elif age <= 20:
        return 1.0
    elif age <= 24:
        return 1.2
    elif age <= 30:
        return 0.8        # still improving
    elif age <= 33:
        return 0.3        # slight gains
    elif age <= 36:
        return -0.2
    else:
        return -0.5


def _defensive_growth_rate(age: int) -> float:
    """Defensive attributes: similar to technical but peak slightly later."""
    if age <= 17:
        return 1.2
    elif age <= 20:
        return 1.2
    elif age <= 24:
        return 1.0
    elif age <= 31:
        return 0.3
    elif age <= 34:
        return -0.2
    else:
        return -0.6


def _gk_growth_rate(age: int) -> float:
    """GK attributes: goalkeepers peak later (28-33)."""
    if age <= 20:
        return 1.4
    elif age <= 24:
        return 1.2
    elif age <= 28:
        return 0.8
    elif age <= 33:
        return 0.3        # GKs stay strong longer
    elif age <= 36:
        return -0.3
    else:
        return -0.8


# Map attribute names to their growth curve function
def _get_growth_rate(attr_name: str, age: int) -> float:
    if attr_name in _PHYSICAL_ATTRS:
        return _physical_growth_rate(age)
    elif attr_name in _TECHNICAL_ATTRS:
        return _technical_growth_rate(age)
    elif attr_name in _MENTAL_ATTRS:
        return _mental_growth_rate(age)
    elif attr_name in _DEFENSIVE_ATTRS:
        return _defensive_growth_rate(age)
    elif attr_name in _GK_ATTRS:
        return _gk_growth_rate(age)
    elif attr_name in _PERSONALITY_ATTRS:
        return _mental_growth_rate(age) * 0.3   # personality changes slowly
    else:
        return _technical_growth_rate(age)


# ── Position-Based Overall Calculation ─────────────────────────────────────

_POSITION_WEIGHTS: dict[str, dict[str, float]] = {
    "GK": {
        "gk_diving": 0.20, "gk_handling": 0.18, "gk_positioning": 0.18,
        "gk_reflexes": 0.20, "gk_kicking": 0.10, "gk_speed": 0.05,
        "composure": 0.05, "reactions": 0.04,
    },
    "CB": {
        "defending": 0.12, "marking": 0.12, "standing_tackle": 0.10,
        "interceptions": 0.10, "heading_accuracy": 0.08, "strength": 0.08,
        "jumping": 0.06, "composure": 0.06, "positioning": 0.08,
        "pace": 0.05, "passing": 0.05, "reactions": 0.05,
        "sliding_tackle": 0.05,
    },
    "LB": {
        "defending": 0.10, "marking": 0.08, "standing_tackle": 0.08,
        "pace": 0.10, "crossing": 0.10, "stamina": 0.08,
        "acceleration": 0.08, "passing": 0.08, "dribbling": 0.06,
        "positioning": 0.06, "interceptions": 0.06, "agility": 0.06,
        "reactions": 0.06,
    },
    "RB": {
        "defending": 0.10, "marking": 0.08, "standing_tackle": 0.08,
        "pace": 0.10, "crossing": 0.10, "stamina": 0.08,
        "acceleration": 0.08, "passing": 0.08, "dribbling": 0.06,
        "positioning": 0.06, "interceptions": 0.06, "agility": 0.06,
        "reactions": 0.06,
    },
    "CDM": {
        "defending": 0.10, "interceptions": 0.10, "standing_tackle": 0.10,
        "positioning": 0.10, "passing": 0.08, "stamina": 0.08,
        "strength": 0.08, "composure": 0.08, "vision": 0.06,
        "reactions": 0.06, "marking": 0.06, "short_passing": 0.05,
        "heading_accuracy": 0.05,
    },
    "CM": {
        "passing": 0.10, "short_passing": 0.08, "vision": 0.10,
        "stamina": 0.08, "ball_control": 0.08, "composure": 0.08,
        "positioning": 0.08, "reactions": 0.06, "long_passing": 0.06,
        "dribbling": 0.06, "interceptions": 0.06, "shooting": 0.05,
        "defending": 0.05, "strength": 0.06,
    },
    "CAM": {
        "vision": 0.12, "passing": 0.10, "dribbling": 0.10,
        "ball_control": 0.10, "composure": 0.08, "finishing": 0.08,
        "agility": 0.08, "short_passing": 0.06, "shooting": 0.06,
        "reactions": 0.06, "long_shots": 0.06, "curve": 0.05,
        "balance": 0.05,
    },
    "LM": {
        "pace": 0.10, "crossing": 0.10, "dribbling": 0.10,
        "stamina": 0.08, "passing": 0.08, "ball_control": 0.08,
        "acceleration": 0.08, "agility": 0.08, "vision": 0.06,
        "finishing": 0.06, "sprint_speed": 0.06, "reactions": 0.06,
        "balance": 0.06,
    },
    "RM": {
        "pace": 0.10, "crossing": 0.10, "dribbling": 0.10,
        "stamina": 0.08, "passing": 0.08, "ball_control": 0.08,
        "acceleration": 0.08, "agility": 0.08, "vision": 0.06,
        "finishing": 0.06, "sprint_speed": 0.06, "reactions": 0.06,
        "balance": 0.06,
    },
    "LW": {
        "pace": 0.12, "dribbling": 0.12, "acceleration": 0.10,
        "ball_control": 0.10, "crossing": 0.08, "agility": 0.08,
        "finishing": 0.08, "sprint_speed": 0.08, "composure": 0.06,
        "vision": 0.06, "balance": 0.06, "reactions": 0.06,
    },
    "RW": {
        "pace": 0.12, "dribbling": 0.12, "acceleration": 0.10,
        "ball_control": 0.10, "crossing": 0.08, "agility": 0.08,
        "finishing": 0.08, "sprint_speed": 0.08, "composure": 0.06,
        "vision": 0.06, "balance": 0.06, "reactions": 0.06,
    },
    "CF": {
        "finishing": 0.12, "shooting": 0.10, "positioning": 0.10,
        "composure": 0.10, "vision": 0.08, "dribbling": 0.08,
        "ball_control": 0.08, "shot_power": 0.06, "reactions": 0.06,
        "passing": 0.06, "agility": 0.06, "long_shots": 0.05,
        "balance": 0.05,
    },
    "ST": {
        "finishing": 0.14, "positioning": 0.10, "shooting": 0.10,
        "composure": 0.08, "heading_accuracy": 0.08, "shot_power": 0.08,
        "pace": 0.06, "strength": 0.06, "reactions": 0.06,
        "ball_control": 0.06, "dribbling": 0.06, "volleys": 0.06,
        "acceleration": 0.06,
    },
    "LWB": {
        "pace": 0.10, "crossing": 0.10, "stamina": 0.10,
        "defending": 0.08, "acceleration": 0.08, "dribbling": 0.08,
        "passing": 0.08, "standing_tackle": 0.06, "marking": 0.06,
        "interceptions": 0.06, "agility": 0.06, "sprint_speed": 0.06,
        "balance": 0.04, "positioning": 0.04,
    },
    "RWB": {
        "pace": 0.10, "crossing": 0.10, "stamina": 0.10,
        "defending": 0.08, "acceleration": 0.08, "dribbling": 0.08,
        "passing": 0.08, "standing_tackle": 0.06, "marking": 0.06,
        "interceptions": 0.06, "agility": 0.06, "sprint_speed": 0.06,
        "balance": 0.04, "positioning": 0.04,
    },
}


def calculate_positional_overall(player: Player) -> int:
    """Calculate overall rating based on position-weighted attributes.

    Falls back to the default position weights for CM if position not found.
    """
    pos = player.position or "CM"
    weights = _POSITION_WEIGHTS.get(pos, _POSITION_WEIGHTS["CM"])

    total = 0.0
    weight_sum = 0.0
    for attr_name, weight in weights.items():
        val = getattr(player, attr_name, 50) or 50
        total += val * weight
        weight_sum += weight

    if weight_sum > 0:
        return max(1, min(99, round(total / weight_sum)))
    return player.overall or 50


# ── Playing Time Impact ────────────────────────────────────────────────────

def _playing_time_multiplier(player: Player, season: int) -> float:
    """Calculate a growth multiplier based on minutes played.

    Young players need playing time to develop. Lack of minutes
    reduces growth significantly.

    Returns 0.3 - 1.5 multiplier.
    """
    age = player.age or 25
    if age > 27:
        return 1.0   # playing time doesn't affect mature players' growth

    minutes = player.minutes_season or 0

    # Expected minutes per season: ~3000 for starters, ~1500 for rotation
    if minutes >= 2500:
        return 1.3    # excellent game time
    elif minutes >= 1500:
        return 1.1    # good rotation
    elif minutes >= 800:
        return 0.9    # some game time
    elif minutes >= 300:
        return 0.6    # barely playing
    elif minutes > 0:
        return 0.4    # token appearances
    else:
        return 0.3    # no playing time at all


# ── Monthly Development Processing ────────────────────────────────────────


class PlayerDevelopmentManager:
    """Manages monthly player development, annual aging, and retirement."""

    def __init__(self, session: DBSession):
        self.session = session

    def process_monthly_development(
        self,
        club_id: Optional[int] = None,
        season: int = 0,
    ):
        """Apply monthly attribute development to players.

        If club_id is provided, only process that club's players.
        Otherwise, process all players in the database.

        Steps per player:
        1. Determine growth/decline rates per attribute category
        2. Apply playing time multiplier (for young players)
        3. Apply professionalism/determination bonus
        4. Roll for each attribute change
        5. Recalculate overall
        """
        if club_id is not None:
            players = (
                self.session.query(Player)
                .filter_by(club_id=club_id)
                .filter(Player.injured_weeks == 0)
                .all()
            )
        else:
            players = (
                self.session.query(Player)
                .filter(Player.injured_weeks == 0)
                .all()
            )

        for player in players:
            self._develop_player(player, season)

        self.session.flush()

    def _develop_player(self, player: Player, season: int):
        """Apply development to a single player for one month."""
        age = player.age or 25
        potential = player.potential or 50
        overall = player.overall or 50

        # Playing time multiplier
        pt_mult = _playing_time_multiplier(player, season)

        # Professionalism / determination bonus (1-99 -> 0.8-1.2)
        prof = (player.professionalism or 50) / 99.0
        det = (player.determination or 50) / 99.0
        character_mult = 0.8 + (prof + det) / 2.0 * 0.4

        # All developable attributes
        all_attrs = (
            _PHYSICAL_ATTRS + _TECHNICAL_ATTRS + _MENTAL_ATTRS
            + _DEFENSIVE_ATTRS
        )
        if player.position == "GK":
            all_attrs = all_attrs + _GK_ATTRS

        for attr_name in all_attrs:
            current_val = getattr(player, attr_name, None)
            if current_val is None:
                continue

            growth_rate = _get_growth_rate(attr_name, age)

            if growth_rate > 0:
                # Growth phase
                # Don't grow much past potential
                if overall >= potential and random.random() > 0.05:
                    continue

                rate = growth_rate * pt_mult * character_mult / 12.0
                # Monthly chance: rate is annual, divide by 12
                rate *= random.uniform(0.5, 1.5)

                int_part = int(rate)
                frac = rate - int_part
                change = int_part + (1 if random.random() < frac else 0)

                if change > 0:
                    new_val = min(99, current_val + change)
                    setattr(player, attr_name, new_val)

            elif growth_rate < 0:
                # Decline phase
                rate = abs(growth_rate) / 12.0
                rate *= random.uniform(0.3, 1.5)

                int_part = int(rate)
                frac = rate - int_part
                change = int_part + (1 if random.random() < frac else 0)

                if change > 0:
                    new_val = max(1, current_val - change)
                    setattr(player, attr_name, new_val)

        # Personality attributes change slowly
        for attr_name in _PERSONALITY_ATTRS:
            current_val = getattr(player, attr_name, None)
            if current_val is None:
                continue
            # Tiny random drift (±1 with small probability)
            if random.random() < 0.05:
                drift = random.choice([-1, 1])
                new_val = max(10, min(90, current_val + drift))
                setattr(player, attr_name, new_val)

        # Recalculate overall
        new_overall = calculate_positional_overall(player)
        player.overall = new_overall

        # Update match sharpness decay if not playing
        if (player.minutes_season or 0) == 0 and age <= 30:
            player.match_sharpness = max(
                20.0, (player.match_sharpness or 70.0) - 1.0,
            )

    # ── Annual aging ───────────────────────────────────────────────────

    def age_all_players(self, session_or_season: int = 0):
        """Age every player by one year and reset seasonal state.

        Called at end of season. Handles:
        - Age increment
        - Seasonal stat reset
        - Retirement checks
        - Contract expiry flags
        """
        season = session_or_season
        players = self.session.query(Player).all()
        retirements = []

        for p in players:
            p.age = (p.age or 25) + 1

            # ── Retirement check ──
            if self._should_retire(p):
                retirements.append(p)

            # ── Reset seasonal state ──
            p.yellow_cards_season = 0
            p.red_cards_season = 0
            p.injured_weeks = 0
            p.suspended_matches = 0
            p.fitness = 100.0
            p.form = 65.0
            p.goals_season = 0
            p.assists_season = 0
            p.minutes_season = 0
            p.match_sharpness = 70.0

        # Process retirements
        for p in retirements:
            self.session.add(NewsItem(
                season=season,
                headline=f"{p.name} announces retirement",
                body=(
                    f"{p.name} has retired from professional football at age {p.age}. "
                    f"Career overall peak: {p.potential or p.overall}."
                ),
                category="general",
            ))
            p.club_id = None

        self.session.flush()
        return retirements

    def _should_retire(self, player: Player) -> bool:
        """Determine if a player should retire."""
        age = player.age or 25
        overall = player.overall or 50

        # Goalkeepers retire later
        is_gk = player.position == "GK"
        retirement_base = 36 if is_gk else 34

        if age >= retirement_base and overall < 55:
            prob = 0.4 + (age - retirement_base) * 0.15
            return random.random() < prob

        hard_cap = 42 if is_gk else 39
        if age >= hard_cap:
            return True

        # Very low overall at any older age
        if age >= 33 and overall < 45:
            return random.random() < 0.5

        return False

    # ── Injury impact on development ───────────────────────────────────

    def process_injury_impact(self, player: Player, injury_weeks: int):
        """Apply development impact from an injury.

        Long injuries can:
        - Reduce physical attributes slightly
        - Reduce match sharpness
        - Rarely reduce potential (serious injuries only)
        """
        if injury_weeks <= 2:
            # Minor injury: just sharpness loss
            player.match_sharpness = max(
                20.0, (player.match_sharpness or 70.0) - injury_weeks * 3.0,
            )
            return

        # Moderate injury (3-8 weeks)
        player.match_sharpness = max(
            10.0, (player.match_sharpness or 70.0) - injury_weeks * 2.5,
        )

        # Physical attribute reduction (small)
        if injury_weeks >= 4:
            attrs_to_reduce = random.sample(
                _PHYSICAL_ATTRS, min(2, len(_PHYSICAL_ATTRS)),
            )
            for attr_name in attrs_to_reduce:
                val = getattr(player, attr_name, 50)
                if val and random.random() < 0.3:
                    setattr(player, attr_name, max(1, val - 1))

        # Serious injury (8+ weeks): potential reduction risk
        if injury_weeks >= 8:
            if random.random() < 0.15:
                reduction = random.randint(1, 2)
                player.potential = max(
                    player.overall or 50,
                    (player.potential or 50) - reduction,
                )

        # Very serious (16+ weeks)
        if injury_weeks >= 16:
            if random.random() < 0.25:
                reduction = random.randint(1, 3)
                player.potential = max(
                    player.overall or 50,
                    (player.potential or 50) - reduction,
                )
                # Direct attribute loss
                attrs_to_reduce = random.sample(
                    _PHYSICAL_ATTRS, min(3, len(_PHYSICAL_ATTRS)),
                )
                for attr_name in attrs_to_reduce:
                    val = getattr(player, attr_name, 50)
                    if val:
                        setattr(player, attr_name, max(1, val - random.randint(1, 2)))

    # ── Weekly injury recovery ─────────────────────────────────────────

    def process_weekly_injuries(self):
        """Process injury recovery for all injured players."""
        players = self.session.query(Player).filter(Player.injured_weeks > 0).all()
        for p in players:
            p.injured_weeks = max(0, (p.injured_weeks or 0) - 1)
            if p.injured_weeks == 0:
                # Returned from injury: not fully fit
                p.fitness = 80.0
                # Sharpness drops proportionally to time out
                p.match_sharpness = max(
                    30.0, (p.match_sharpness or 70.0) - 5.0,
                )
        self.session.flush()


# ── Module-level convenience functions (backward compatible) ───────────────


def age_all_players(session: DBSession, season: int = 0):
    """Age every player by one year. Backward-compatible wrapper."""
    mgr = PlayerDevelopmentManager(session)
    return mgr.age_all_players(season)


def process_weekly_injuries(session: DBSession):
    """Process weekly injury recovery. Backward-compatible wrapper."""
    mgr = PlayerDevelopmentManager(session)
    mgr.process_weekly_injuries()
