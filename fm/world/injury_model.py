"""Realistic injury generation, recovery, and fitness-on-return model."""
from __future__ import annotations

import enum
import random
from dataclasses import dataclass

from fm.db.models import Injury
from fm.utils.helpers import clamp


# ── Injury type enum ──────────────────────────────────────────────────────


class InjuryType(str, enum.Enum):
    HAMSTRING = "hamstring"
    ANKLE = "ankle"
    KNEE_ACL = "knee_acl"
    KNEE_MCL = "knee_mcl"
    GROIN = "groin"
    CALF = "calf"
    THIGH = "thigh"
    BACK = "back"
    SHOULDER = "shoulder"
    CONCUSSION = "concussion"
    FOOT = "foot"
    HIP = "hip"


# ── Severity levels (must match Injury.severity column) ──────────────────

_MINOR = "minor"
_MODERATE = "moderate"
_SERIOUS = "serious"
_CAREER = "career_threatening"


# ── Per-type profiles ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class _InjuryProfile:
    """Statistical profile for one injury type."""

    # Severity weights: [minor, moderate, serious, career_threatening]
    severity_weights: tuple[float, float, float, float]
    # Recovery range in weeks per severity bucket
    recovery_ranges: dict[str, tuple[int, int]]
    # Setback chance range (low, high)
    setback_chance_range: tuple[float, float]
    # Weeks of elevated re-injury risk after return
    reinjury_window: int


INJURY_PROFILES: dict[InjuryType, _InjuryProfile] = {
    InjuryType.HAMSTRING: _InjuryProfile(
        severity_weights=(0.15, 0.60, 0.25, 0.00),
        recovery_ranges={_MINOR: (1, 2), _MODERATE: (2, 5), _SERIOUS: (5, 8), _CAREER: (8, 12)},
        setback_chance_range=(0.05, 0.15),
        reinjury_window=4,
    ),
    InjuryType.ANKLE: _InjuryProfile(
        severity_weights=(0.25, 0.45, 0.25, 0.05),
        recovery_ranges={_MINOR: (1, 2), _MODERATE: (2, 4), _SERIOUS: (4, 8), _CAREER: (8, 16)},
        setback_chance_range=(0.05, 0.12),
        reinjury_window=3,
    ),
    InjuryType.KNEE_ACL: _InjuryProfile(
        severity_weights=(0.00, 0.00, 0.30, 0.70),
        recovery_ranges={_MINOR: (4, 6), _MODERATE: (6, 12), _SERIOUS: (20, 30), _CAREER: (30, 40)},
        setback_chance_range=(0.10, 0.25),
        reinjury_window=8,
    ),
    InjuryType.KNEE_MCL: _InjuryProfile(
        severity_weights=(0.10, 0.40, 0.40, 0.10),
        recovery_ranges={_MINOR: (1, 3), _MODERATE: (3, 6), _SERIOUS: (6, 12), _CAREER: (12, 20)},
        setback_chance_range=(0.08, 0.18),
        reinjury_window=6,
    ),
    InjuryType.GROIN: _InjuryProfile(
        severity_weights=(0.20, 0.50, 0.25, 0.05),
        recovery_ranges={_MINOR: (1, 2), _MODERATE: (2, 4), _SERIOUS: (4, 8), _CAREER: (8, 14)},
        setback_chance_range=(0.06, 0.14),
        reinjury_window=4,
    ),
    InjuryType.CALF: _InjuryProfile(
        severity_weights=(0.20, 0.55, 0.20, 0.05),
        recovery_ranges={_MINOR: (1, 2), _MODERATE: (2, 4), _SERIOUS: (4, 7), _CAREER: (7, 12)},
        setback_chance_range=(0.05, 0.12),
        reinjury_window=3,
    ),
    InjuryType.THIGH: _InjuryProfile(
        severity_weights=(0.20, 0.50, 0.25, 0.05),
        recovery_ranges={_MINOR: (1, 2), _MODERATE: (2, 4), _SERIOUS: (4, 7), _CAREER: (7, 12)},
        setback_chance_range=(0.05, 0.13),
        reinjury_window=4,
    ),
    InjuryType.BACK: _InjuryProfile(
        severity_weights=(0.15, 0.45, 0.30, 0.10),
        recovery_ranges={_MINOR: (1, 3), _MODERATE: (3, 6), _SERIOUS: (6, 12), _CAREER: (12, 20)},
        setback_chance_range=(0.08, 0.20),
        reinjury_window=5,
    ),
    InjuryType.SHOULDER: _InjuryProfile(
        severity_weights=(0.25, 0.45, 0.25, 0.05),
        recovery_ranges={_MINOR: (1, 2), _MODERATE: (2, 4), _SERIOUS: (4, 8), _CAREER: (8, 16)},
        setback_chance_range=(0.04, 0.10),
        reinjury_window=3,
    ),
    InjuryType.CONCUSSION: _InjuryProfile(
        severity_weights=(0.30, 0.50, 0.15, 0.05),
        recovery_ranges={_MINOR: (1, 1), _MODERATE: (1, 3), _SERIOUS: (3, 6), _CAREER: (6, 12)},
        setback_chance_range=(0.03, 0.08),
        reinjury_window=4,
    ),
    InjuryType.FOOT: _InjuryProfile(
        severity_weights=(0.20, 0.50, 0.25, 0.05),
        recovery_ranges={_MINOR: (1, 2), _MODERATE: (2, 5), _SERIOUS: (5, 10), _CAREER: (10, 18)},
        setback_chance_range=(0.05, 0.12),
        reinjury_window=3,
    ),
    InjuryType.HIP: _InjuryProfile(
        severity_weights=(0.15, 0.45, 0.30, 0.10),
        recovery_ranges={_MINOR: (1, 3), _MODERATE: (3, 6), _SERIOUS: (6, 12), _CAREER: (12, 20)},
        setback_chance_range=(0.06, 0.15),
        reinjury_window=5,
    ),
}


# ── Position-based injury-type weights ────────────────────────────────────
# Defenders are more prone to ankle / knee injuries; forwards to hamstring / groin.

_DEFENDER_POSITIONS = {"CB", "LB", "RB", "LWB", "RWB"}
_MIDFIELDER_POSITIONS = {"CDM", "CM", "CAM", "LM", "RM"}
_FORWARD_POSITIONS = {"LW", "RW", "CF", "ST"}

_POSITION_WEIGHTS: dict[str, dict[InjuryType, float]] = {
    "defender": {
        InjuryType.HAMSTRING: 0.10, InjuryType.ANKLE: 0.20, InjuryType.KNEE_ACL: 0.08,
        InjuryType.KNEE_MCL: 0.10, InjuryType.GROIN: 0.08, InjuryType.CALF: 0.08,
        InjuryType.THIGH: 0.08, InjuryType.BACK: 0.08, InjuryType.SHOULDER: 0.06,
        InjuryType.CONCUSSION: 0.05, InjuryType.FOOT: 0.05, InjuryType.HIP: 0.04,
    },
    "midfielder": {
        InjuryType.HAMSTRING: 0.15, InjuryType.ANKLE: 0.12, InjuryType.KNEE_ACL: 0.06,
        InjuryType.KNEE_MCL: 0.08, InjuryType.GROIN: 0.10, InjuryType.CALF: 0.10,
        InjuryType.THIGH: 0.10, InjuryType.BACK: 0.07, InjuryType.SHOULDER: 0.04,
        InjuryType.CONCUSSION: 0.04, InjuryType.FOOT: 0.07, InjuryType.HIP: 0.07,
    },
    "forward": {
        InjuryType.HAMSTRING: 0.22, InjuryType.ANKLE: 0.10, InjuryType.KNEE_ACL: 0.06,
        InjuryType.KNEE_MCL: 0.06, InjuryType.GROIN: 0.15, InjuryType.CALF: 0.10,
        InjuryType.THIGH: 0.10, InjuryType.BACK: 0.04, InjuryType.SHOULDER: 0.03,
        InjuryType.CONCUSSION: 0.03, InjuryType.FOOT: 0.06, InjuryType.HIP: 0.05,
    },
    "goalkeeper": {
        InjuryType.HAMSTRING: 0.10, InjuryType.ANKLE: 0.12, InjuryType.KNEE_ACL: 0.06,
        InjuryType.KNEE_MCL: 0.08, InjuryType.GROIN: 0.08, InjuryType.CALF: 0.08,
        InjuryType.THIGH: 0.06, InjuryType.BACK: 0.10, InjuryType.SHOULDER: 0.12,
        InjuryType.CONCUSSION: 0.06, InjuryType.FOOT: 0.06, InjuryType.HIP: 0.08,
    },
}


def _position_group(position: str) -> str:
    """Map a player position code to a broad group key."""
    if position == "GK":
        return "goalkeeper"
    if position in _DEFENDER_POSITIONS:
        return "defender"
    if position in _MIDFIELDER_POSITIONS:
        return "midfielder"
    if position in _FORWARD_POSITIONS:
        return "forward"
    return "midfielder"  # fallback


# ── Injury generator ─────────────────────────────────────────────────────


class InjuryGenerator:
    """Generates realistic injuries and manages recovery progression."""

    # Base chance per action tick (tuned low — many ticks per match)
    BASE_CHANCE: float = 0.00008

    def generate_injury(
        self,
        player_proneness: int,
        fatigue: float,
        minutes_played: int,
        is_training: bool = False,
        position: str = "CM",
        player_id: int | None = None,
        club_id: int | None = None,
        season: int = 1,
        matchday: int = 0,
        overtraining: bool = False,
    ) -> Injury | None:
        """Roll for an injury and return a populated (uncommitted) :class:`Injury`, or *None*.

        Parameters
        ----------
        player_proneness:
            Player's ``injury_proneness`` attribute (1-99).
        fatigue:
            Current fitness level 0-100 (lower = more fatigued).
        minutes_played:
            Minutes the player has been on the pitch this match.
        is_training:
            Whether the injury check is during training (slightly lower base).
        position:
            Player's position code for type-weighting.
        overtraining:
            Whether the overtraining flag is active (multiplies chance).
        """
        chance = self.BASE_CHANCE

        # Proneness modifier: higher proneness => higher chance
        chance *= 1.0 + (player_proneness / 50.0) * 1.5

        # Fatigue modifier: lower fitness => higher chance
        chance *= 1.0 + ((100.0 - fatigue) / 100.0) * 0.5

        # Late-match fatigue spike
        if minutes_played > 80:
            chance *= 1.3

        # Training is slightly safer than competitive matches
        if is_training:
            chance *= 0.7

        # Overtraining flag
        if overtraining:
            chance *= 1.5

        if random.random() > chance:
            return None

        # ── Pick injury type weighted by position ─────────────────────────
        group = _position_group(position)
        weights_map = _POSITION_WEIGHTS[group]
        types = list(weights_map.keys())
        type_weights = [weights_map[t] for t in types]
        injury_type: InjuryType = random.choices(types, weights=type_weights, k=1)[0]

        profile = INJURY_PROFILES[injury_type]

        # ── Pick severity ─────────────────────────────────────────────────
        severities = [_MINOR, _MODERATE, _SERIOUS, _CAREER]
        severity: str = random.choices(
            severities, weights=list(profile.severity_weights), k=1,
        )[0]

        # ── Calculate recovery weeks ──────────────────────────────────────
        lo, hi = profile.recovery_ranges[severity]
        recovery_weeks = random.randint(lo, hi)

        # ── Setback chance ────────────────────────────────────────────────
        sb_lo, sb_hi = profile.setback_chance_range
        setback_chance = round(random.uniform(sb_lo, sb_hi), 3)

        # ── Recovery curve ────────────────────────────────────────────────
        if severity == _CAREER:
            curve = "setback_risk"
        elif severity == _SERIOUS:
            curve = "exponential"
        else:
            curve = "linear"

        # ── Fitness on return ─────────────────────────────────────────────
        fitness_on_return = self.calculate_fitness_on_return_static(severity, recovery_weeks)

        return Injury(
            player_id=player_id or 0,
            club_id=club_id,
            season=season,
            matchday_occurred=matchday,
            injury_type=injury_type.value,
            severity=severity,
            recovery_weeks_total=recovery_weeks,
            recovery_weeks_remaining=recovery_weeks,
            recovery_curve=curve,
            setback_chance=setback_chance,
            fitness_on_return=fitness_on_return,
            reinjury_window_weeks=profile.reinjury_window,
            is_active=True,
        )

    # ── Recovery processing ───────────────────────────────────────────────

    @staticmethod
    def process_recovery(injury: Injury) -> bool:
        """Advance recovery by one week.  Returns *True* if the player has recovered."""
        if not injury.is_active:
            return True

        curve = injury.recovery_curve or "linear"

        if curve == "linear":
            injury.recovery_weeks_remaining = max(injury.recovery_weeks_remaining - 1, 0)

        elif curve == "exponential":
            # Faster early, slower later.  Decrement at least 1.
            total = max(injury.recovery_weeks_total, 1)
            remaining = injury.recovery_weeks_remaining
            progress_ratio = 1.0 - (remaining / total)
            # Early weeks: subtract up to 2; late weeks: subtract 1
            decrement = 2 if progress_ratio < 0.5 else 1
            injury.recovery_weeks_remaining = max(remaining - decrement, 0)

        elif curve == "setback_risk":
            injury.recovery_weeks_remaining = max(injury.recovery_weeks_remaining - 1, 0)
            # Check for setback
            if injury.recovery_weeks_remaining > 0 and random.random() < injury.setback_chance:
                added = random.randint(1, 3)
                injury.recovery_weeks_remaining += added
                injury.recovery_weeks_total += added

        else:
            # Unknown curve type — fall back to linear
            injury.recovery_weeks_remaining = max(injury.recovery_weeks_remaining - 1, 0)

        if injury.recovery_weeks_remaining <= 0:
            injury.is_active = False
            return True

        return False

    # ── Fitness calculation ───────────────────────────────────────────────

    @staticmethod
    def calculate_fitness_on_return(injury: Injury) -> float:
        """Compute the fitness percentage the player will have when recovered."""
        return InjuryGenerator.calculate_fitness_on_return_static(
            injury.severity, injury.recovery_weeks_total,
        )

    @staticmethod
    def calculate_fitness_on_return_static(severity: str, recovery_weeks: int) -> float:
        """Compute fitness-on-return from severity and total recovery weeks.

        Longer absences reduce the return fitness slightly within the base
        for that severity bracket.
        """
        base_map = {
            _MINOR: 90.0,
            _MODERATE: 80.0,
            _SERIOUS: 75.0,
            _CAREER: 70.0,
        }
        base = base_map.get(severity, 80.0)
        # Longer recovery → slightly lower return fitness (max -5)
        penalty = min(recovery_weeks * 0.3, 5.0)
        return round(clamp(base - penalty, 50.0, 95.0), 1)
