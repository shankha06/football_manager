"""Comprehensive training system with staff quality, facilities, intensity,
individual programs, and match preparation.

Training sessions develop player attributes based on:
- Session type (8 types covering all aspects of the game)
- Staff coaching quality (multiplier from Staff model)
- Facility level (multiplier from Club model)
- Training intensity (5 levels: recovery to double session)
- Age-based growth rate (young=2x, peak=1x, old=0.5x)
- Injury risk calculation

Supports both team-wide and individual player training programs.
"""
from __future__ import annotations

import enum
import json
import math
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from fm.db.models import Club, Player, Staff, TrainingSchedule, NewsItem


# ── Enums ──────────────────────────────────────────────────────────────────


class TrainingIntensity(str, enum.Enum):
    RECOVERY = "recovery"
    LIGHT = "light"
    NORMAL = "normal"
    INTENSE = "intense"
    DOUBLE = "double"


class SessionType(str, enum.Enum):
    ATTACKING_MOVEMENT = "attacking_movement"
    DEFENSIVE_SHAPE = "defensive_shape"
    POSSESSION = "possession"
    COUNTER_ATTACKING = "counter_attacking"
    SET_PIECES = "set_pieces"
    PHYSICAL_CONDITIONING = "physical_conditioning"
    TACTICAL_DRILLS = "tactical_drills"
    MATCH_PREPARATION = "match_preparation"


# ── Training Session Definition ────────────────────────────────────────────


@dataclass
class TrainingSession:
    """Describes a single training session and its effects."""
    session_type: SessionType
    attributes_affected: dict[str, float]   # attr_name -> base_increment
    fitness_cost: float                     # 0-100 fitness lost
    injury_risk: float                      # base probability 0.0-1.0
    morale_impact: float = 0.0             # positive = morale boost
    sharpness_gain: float = 0.0            # match_sharpness improvement
    familiarity_gain: float = 0.0          # tactical_familiarity improvement
    description: str = ""


# ── Intensity Multipliers ──────────────────────────────────────────────────

_INTENSITY_CONFIG: dict[TrainingIntensity, dict[str, float]] = {
    TrainingIntensity.RECOVERY: {
        "attr_mult": 0.0,       # no attribute growth
        "fitness_cost": -8.0,   # negative = fitness recovery
        "injury_mult": 0.0,
        "morale_boost": 1.0,
        "sharpness_mult": 0.2,
    },
    TrainingIntensity.LIGHT: {
        "attr_mult": 0.5,
        "fitness_cost": 2.0,
        "injury_mult": 0.3,
        "morale_boost": 0.5,
        "sharpness_mult": 0.6,
    },
    TrainingIntensity.NORMAL: {
        "attr_mult": 1.0,
        "fitness_cost": 4.0,
        "injury_mult": 1.0,
        "morale_boost": 0.0,
        "sharpness_mult": 1.0,
    },
    TrainingIntensity.INTENSE: {
        "attr_mult": 1.5,
        "fitness_cost": 7.0,
        "injury_mult": 2.0,
        "morale_boost": -1.0,
        "sharpness_mult": 1.3,
    },
    TrainingIntensity.DOUBLE: {
        "attr_mult": 2.0,
        "fitness_cost": 12.0,
        "injury_mult": 3.5,
        "morale_boost": -2.5,
        "sharpness_mult": 1.6,
    },
}


# ── Session Type Definitions ───────────────────────────────────────────────

SESSION_DEFINITIONS: dict[SessionType, TrainingSession] = {
    SessionType.ATTACKING_MOVEMENT: TrainingSession(
        session_type=SessionType.ATTACKING_MOVEMENT,
        attributes_affected={
            "finishing": 0.35,
            "shooting": 0.30,
            "positioning": 0.25,
            "long_shots": 0.20,
            "volleys": 0.15,
            "composure": 0.15,
            "vision": 0.10,
            "att_work_rate_boost": 0.10,
        },
        fitness_cost=4.0,
        injury_risk=0.02,
        sharpness_gain=3.0,
        description="Work on attacking movement, finishing drills, and shooting practice.",
    ),
    SessionType.DEFENSIVE_SHAPE: TrainingSession(
        session_type=SessionType.DEFENSIVE_SHAPE,
        attributes_affected={
            "marking": 0.35,
            "standing_tackle": 0.30,
            "sliding_tackle": 0.25,
            "interceptions": 0.30,
            "heading_accuracy": 0.15,
            "positioning": 0.20,
            "composure": 0.10,
            "def_work_rate_boost": 0.10,
        },
        fitness_cost=4.5,
        injury_risk=0.03,
        sharpness_gain=2.5,
        description="Defensive shape, positioning, tackling, and aerial duels.",
    ),
    SessionType.POSSESSION: TrainingSession(
        session_type=SessionType.POSSESSION,
        attributes_affected={
            "short_passing": 0.35,
            "ball_control": 0.30,
            "vision": 0.25,
            "dribbling": 0.20,
            "composure": 0.20,
            "long_passing": 0.15,
            "balance": 0.10,
            "agility": 0.10,
        },
        fitness_cost=3.5,
        injury_risk=0.015,
        sharpness_gain=2.0,
        description="Keep-ball drills, passing triangles, and ball retention.",
    ),
    SessionType.COUNTER_ATTACKING: TrainingSession(
        session_type=SessionType.COUNTER_ATTACKING,
        attributes_affected={
            "acceleration": 0.20,
            "sprint_speed": 0.20,
            "passing": 0.25,
            "vision": 0.25,
            "crossing": 0.20,
            "finishing": 0.20,
            "reactions": 0.15,
            "positioning": 0.15,
        },
        fitness_cost=5.0,
        injury_risk=0.025,
        sharpness_gain=3.0,
        description="Quick transitions, through balls, and finishing on the break.",
    ),
    SessionType.SET_PIECES: TrainingSession(
        session_type=SessionType.SET_PIECES,
        attributes_affected={
            "free_kick_accuracy": 0.40,
            "penalties": 0.35,
            "heading_accuracy": 0.30,
            "curve": 0.25,
            "crossing": 0.20,
            "jumping": 0.10,
            "positioning": 0.15,
        },
        fitness_cost=2.5,
        injury_risk=0.01,
        sharpness_gain=1.5,
        description="Corner routines, free kick practice, and penalty drills.",
    ),
    SessionType.PHYSICAL_CONDITIONING: TrainingSession(
        session_type=SessionType.PHYSICAL_CONDITIONING,
        attributes_affected={
            "stamina": 0.30,
            "strength": 0.25,
            "pace": 0.15,
            "acceleration": 0.15,
            "sprint_speed": 0.15,
            "jumping": 0.15,
            "agility": 0.15,
            "balance": 0.10,
        },
        fitness_cost=7.0,
        injury_risk=0.035,
        morale_impact=-0.5,
        sharpness_gain=1.0,
        description="Gym work, interval training, sprint drills, and endurance runs.",
    ),
    SessionType.TACTICAL_DRILLS: TrainingSession(
        session_type=SessionType.TACTICAL_DRILLS,
        attributes_affected={
            "positioning": 0.35,
            "vision": 0.30,
            "composure": 0.25,
            "reactions": 0.20,
            "short_passing": 0.15,
            "marking": 0.15,
            "interceptions": 0.15,
        },
        fitness_cost=3.0,
        injury_risk=0.015,
        familiarity_gain=5.0,
        sharpness_gain=2.0,
        description="Shape work, positional play, pressing triggers, and build-up patterns.",
    ),
    SessionType.MATCH_PREPARATION: TrainingSession(
        session_type=SessionType.MATCH_PREPARATION,
        attributes_affected={},   # no permanent attribute growth
        fitness_cost=2.0,
        injury_risk=0.01,
        familiarity_gain=8.0,
        sharpness_gain=5.0,
        morale_impact=1.0,
        description="Match simulation, set-piece rehearsal, and opponent analysis.",
    ),
}


# ── Staff Quality Helpers ──────────────────────────────────────────────────

def _get_coaching_quality(session: DBSession, club_id: int, session_type: SessionType) -> float:
    """Return average coaching quality (0.5-1.5) for the session type.

    Maps session type to relevant staff coaching attributes, queries all
    coaches at the club, and returns a normalised multiplier.
    """
    # Map session types to the most relevant coaching attributes
    _type_to_attrs: dict[SessionType, list[str]] = {
        SessionType.ATTACKING_MOVEMENT: ["coaching_attacking", "coaching_technical"],
        SessionType.DEFENSIVE_SHAPE: ["coaching_defending", "coaching_tactical"],
        SessionType.POSSESSION: ["coaching_technical", "coaching_tactical"],
        SessionType.COUNTER_ATTACKING: ["coaching_attacking", "coaching_tactical"],
        SessionType.SET_PIECES: ["coaching_technical", "coaching_attacking"],
        SessionType.PHYSICAL_CONDITIONING: ["coaching_fitness", "coaching_mental"],
        SessionType.TACTICAL_DRILLS: ["coaching_tactical", "coaching_mental"],
        SessionType.MATCH_PREPARATION: ["coaching_tactical", "coaching_attacking", "coaching_defending"],
    }

    attr_names = _type_to_attrs.get(session_type, ["coaching_tactical"])

    coaches = (
        session.query(Staff)
        .filter(
            Staff.club_id == club_id,
            Staff.role.in_(["head_coach", "assistant", "gk_coach", "fitness_coach", "youth_coach"]),
        )
        .all()
    )

    if not coaches:
        return 1.0  # no staff => neutral

    total = 0.0
    count = 0
    for coach in coaches:
        for attr_name in attr_names:
            val = getattr(coach, attr_name, 50) or 50
            total += val
            count += 1

    if count == 0:
        return 1.0

    avg = total / count   # 1-99 scale
    # Map 1-99 to 0.5-1.5 multiplier
    return 0.5 + (avg / 99.0)


def _get_facility_multiplier(session: DBSession, club_id: int) -> float:
    """Return training facility multiplier (0.6-1.4) based on club level."""
    club = session.get(Club, club_id)
    if not club:
        return 1.0
    level = club.training_facility_level or 5
    # 1 -> 0.6, 5 -> 1.0, 10 -> 1.4
    return 0.6 + (level - 1) * (0.8 / 9.0)


# ── Age-Based Growth Rates ─────────────────────────────────────────────────

def _age_multiplier(age: int) -> float:
    """Return growth multiplier based on player age.

    - Under 18: 2.0x  (rapid development)
    - 18-20:    1.8x
    - 21-23:    1.4x
    - 24-27:    1.0x  (peak baseline)
    - 28-29:    0.7x
    - 30-32:    0.4x
    - 33+:      0.2x  (minimal growth)
    """
    if age < 18:
        return 2.0
    elif age <= 20:
        return 1.8
    elif age <= 23:
        return 1.4
    elif age <= 27:
        return 1.0
    elif age <= 29:
        return 0.7
    elif age <= 32:
        return 0.4
    else:
        return 0.2


# ── Injury Risk Calculation ────────────────────────────────────────────────

def _calculate_injury_risk(
    player: Player,
    base_risk: float,
    intensity_mult: float,
) -> float:
    """Calculate injury probability for a training session.

    Factors:
    - Base risk of the session type
    - Intensity multiplier
    - Player fitness (low fitness = higher risk)
    - Player injury_proneness attribute
    - Player age (older = slightly more risk)
    """
    fitness = player.fitness or 100.0
    proneness = (player.injury_proneness or 30) / 99.0   # 0.0-1.0
    age_factor = 1.0
    age = player.age or 25
    if age >= 32:
        age_factor = 1.3 + (age - 32) * 0.1
    elif age >= 28:
        age_factor = 1.1

    # Low fitness dramatically increases risk
    fitness_factor = 1.0
    if fitness < 40:
        fitness_factor = 2.5
    elif fitness < 60:
        fitness_factor = 1.8
    elif fitness < 75:
        fitness_factor = 1.3

    risk = base_risk * intensity_mult * (0.5 + proneness) * age_factor * fitness_factor
    return min(risk, 0.25)  # cap at 25%


def _apply_training_injury(
    session: DBSession,
    player: Player,
    risk: float,
    season: int,
    matchday: int,
) -> bool:
    """Roll for injury and apply if triggered. Returns True if injured."""
    if random.random() >= risk:
        return False

    # Determine severity based on risk level
    roll = random.random()
    if roll < 0.5:
        weeks = 1   # minor knock
        desc = "minor knock in training"
    elif roll < 0.8:
        weeks = random.randint(2, 4)
        desc = "muscle strain during training"
    elif roll < 0.95:
        weeks = random.randint(4, 8)
        desc = "ligament injury sustained in training"
    else:
        weeks = random.randint(8, 16)
        desc = "serious injury in training"

    player.injured_weeks = weeks
    player.fitness = max(20.0, (player.fitness or 100.0) - 20.0)
    player.match_sharpness = max(0.0, (player.match_sharpness or 70.0) - 15.0)

    session.add(NewsItem(
        season=season,
        matchday=matchday,
        headline=f"{player.name} injured in training",
        body=f"{player.name} has suffered a {desc}. Expected return: {weeks} week(s).",
        category="injury",
    ))

    return True


# ── Main Training Manager ─────────────────────────────────────────────────


class TrainingManager:
    """Manages weekly training sessions for clubs.

    Supports:
    - Team-wide training with 8 session types
    - 5 intensity levels from recovery to double sessions
    - Staff coaching quality multipliers
    - Facility level multipliers
    - Age-based growth rates
    - Individual training programs
    - Match preparation (boosts tactical familiarity and sharpness)
    - Injury risk calculation
    """

    def __init__(self, session: DBSession):
        self.session = session

    # ── Public: focus management (backward compatible) ─────────────────

    def set_focus(self, club_id: int, focus: str):
        """Set the team's training focus (backward compatible string API)."""
        club = self.session.get(Club, club_id)
        if club:
            club.training_focus = focus
            self.session.flush()

    def get_focus(self, club_id: int) -> str:
        """Return the current training focus string for a club."""
        club = self.session.get(Club, club_id)
        if club and club.training_focus:
            return club.training_focus
        return "match_prep"

    # ── Public: intensity management ───────────────────────────────────

    def set_intensity(self, club_id: int, intensity: TrainingIntensity):
        """Set training intensity via a TrainingSchedule row."""
        schedule = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id, player_id=None)
            .first()
        )
        if schedule:
            schedule.intensity = intensity.value
        else:
            schedule = TrainingSchedule(
                club_id=club_id,
                focus=self.get_focus(club_id),
                intensity=intensity.value,
            )
            self.session.add(schedule)
        self.session.flush()

    def get_intensity(self, club_id: int) -> TrainingIntensity:
        """Return current training intensity for the club."""
        schedule = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id, player_id=None)
            .first()
        )
        if schedule and schedule.intensity:
            try:
                return TrainingIntensity(schedule.intensity)
            except ValueError:
                pass
        return TrainingIntensity.NORMAL

    # ── Public: individual training ────────────────────────────────────

    def set_individual_training(
        self,
        club_id: int,
        player_id: int,
        target_attrs: list[str],
        intensity: TrainingIntensity = TrainingIntensity.NORMAL,
        duration_weeks: int = 4,
    ):
        """Assign an individual training program to a player.

        target_attrs: list of attribute names to focus on, e.g. ["finishing", "composure"]
        """
        # Remove any existing individual schedule
        existing = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id, player_id=player_id)
            .first()
        )
        if existing:
            self.session.delete(existing)

        schedule = TrainingSchedule(
            club_id=club_id,
            player_id=player_id,
            focus="individual",
            intensity=intensity.value,
            duration_weeks=duration_weeks,
            weeks_completed=0,
            individual_attrs=json.dumps(target_attrs),
        )
        self.session.add(schedule)
        self.session.flush()

    def cancel_individual_training(self, club_id: int, player_id: int):
        """Cancel a player's individual training program."""
        existing = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id, player_id=player_id)
            .first()
        )
        if existing:
            self.session.delete(existing)
            self.session.flush()

    def get_individual_training(self, club_id: int, player_id: int) -> Optional[dict]:
        """Return current individual training info, or None."""
        schedule = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id, player_id=player_id)
            .first()
        )
        if not schedule:
            return None
        attrs = []
        if schedule.individual_attrs:
            try:
                attrs = json.loads(schedule.individual_attrs)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "attrs": attrs,
            "intensity": schedule.intensity,
            "duration_weeks": schedule.duration_weeks,
            "weeks_completed": schedule.weeks_completed,
        }

    # ── Public: match preparation ──────────────────────────────────────

    def set_match_preparation(self, club_id: int, opponent_id: int):
        """Set the club to prepare for a specific opponent this week."""
        schedule = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id, player_id=None)
            .first()
        )
        if schedule:
            schedule.is_match_prep = True
            schedule.opponent_id = opponent_id
            schedule.focus = SessionType.MATCH_PREPARATION.value
        else:
            schedule = TrainingSchedule(
                club_id=club_id,
                focus=SessionType.MATCH_PREPARATION.value,
                intensity=TrainingIntensity.NORMAL.value,
                is_match_prep=True,
                opponent_id=opponent_id,
            )
            self.session.add(schedule)
        self.session.flush()

    # ── Public: weekly processing ──────────────────────────────────────

    def process_weekly_training(
        self,
        club_id: int,
        season: int = 0,
        matchday: int = 0,
    ):
        """Apply training effects to all squad players for the week.

        This is the main entry point called by the season manager each week.
        Steps:
        1. Determine session type from club focus
        2. Get intensity, coaching quality, facility multiplier
        3. For each non-injured player:
           a. Calculate attribute growth (team + individual)
           b. Apply fitness cost / recovery
           c. Apply morale impact
           d. Update match sharpness and tactical familiarity
           e. Roll for training injury
        """
        focus_str = self.get_focus(club_id)
        intensity = self.get_intensity(club_id)
        int_config = _INTENSITY_CONFIG[intensity]

        # Map old-style focus strings to session types
        session_type = self._map_focus_to_session(focus_str)
        session_def = SESSION_DEFINITIONS[session_type]

        # Multipliers
        coaching_mult = _get_coaching_quality(self.session, club_id, session_type)
        facility_mult = _get_facility_multiplier(self.session, club_id)
        attr_mult = int_config["attr_mult"]

        # Fetch non-injured players
        players = (
            self.session.query(Player)
            .filter_by(club_id=club_id)
            .filter(Player.injured_weeks == 0)
            .all()
        )

        for player in players:
            age = player.age or 25
            age_mult = _age_multiplier(age)

            # ── Attribute growth (team session) ──
            if attr_mult > 0 and session_def.attributes_affected:
                self._apply_attribute_growth(
                    player, session_def.attributes_affected,
                    base_mult=attr_mult * coaching_mult * facility_mult * age_mult,
                )

            # ── Individual training on top ──
            self._apply_individual_training(
                player, club_id,
                coaching_mult=coaching_mult,
                facility_mult=facility_mult,
                age_mult=age_mult,
            )

            # ── Fitness cost ──
            fitness_delta = int_config["fitness_cost"]
            if session_def.session_type == SessionType.MATCH_PREPARATION:
                fitness_delta *= 0.5  # match prep is lighter
            player.fitness = max(0.0, min(100.0, (player.fitness or 100.0) - fitness_delta))

            # ── Morale impact ──
            morale_delta = (
                session_def.morale_impact + int_config["morale_boost"]
            )
            if morale_delta != 0:
                player.morale = max(0.0, min(100.0, (player.morale or 65.0) + morale_delta))

            # ── Match sharpness ──
            sharpness_gain = session_def.sharpness_gain * int_config["sharpness_mult"]
            player.match_sharpness = max(0.0, min(
                100.0, (player.match_sharpness or 70.0) + sharpness_gain,
            ))

            # ── Tactical familiarity ──
            fam_gain = session_def.familiarity_gain
            if fam_gain > 0:
                player.tactical_familiarity = max(0.0, min(
                    100.0, (player.tactical_familiarity or 50.0) + fam_gain,
                ))

            # ── Injury risk ──
            injury_risk = _calculate_injury_risk(
                player, session_def.injury_risk, int_config["injury_mult"],
            )
            _apply_training_injury(self.session, player, injury_risk, season, matchday)

        # ── Update individual training progress ──
        self._tick_individual_schedules(club_id)

        self.session.flush()

    def process_rest_day(self, club_id: int):
        """Rest day - recover fitness for all squad players."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        for player in players:
            if (player.injured_weeks or 0) > 0:
                recovery = 2.0
            else:
                recovery = 8.0
            player.fitness = min(100.0, (player.fitness or 100.0) + recovery)
            # Slight sharpness decay on rest days
            player.match_sharpness = max(
                0.0, (player.match_sharpness or 70.0) - 0.5,
            )
        self.session.flush()

    # ── Internal helpers ───────────────────────────────────────────────

    def _map_focus_to_session(self, focus: str) -> SessionType:
        """Map legacy training focus strings to SessionType."""
        _mapping = {
            "attacking": SessionType.ATTACKING_MOVEMENT,
            "defending": SessionType.DEFENSIVE_SHAPE,
            "physical": SessionType.PHYSICAL_CONDITIONING,
            "tactical": SessionType.TACTICAL_DRILLS,
            "set_pieces": SessionType.SET_PIECES,
            "match_prep": SessionType.MATCH_PREPARATION,
            # Direct session type values pass through
            SessionType.ATTACKING_MOVEMENT.value: SessionType.ATTACKING_MOVEMENT,
            SessionType.DEFENSIVE_SHAPE.value: SessionType.DEFENSIVE_SHAPE,
            SessionType.POSSESSION.value: SessionType.POSSESSION,
            SessionType.COUNTER_ATTACKING.value: SessionType.COUNTER_ATTACKING,
            SessionType.SET_PIECES.value: SessionType.SET_PIECES,
            SessionType.PHYSICAL_CONDITIONING.value: SessionType.PHYSICAL_CONDITIONING,
            SessionType.TACTICAL_DRILLS.value: SessionType.TACTICAL_DRILLS,
            SessionType.MATCH_PREPARATION.value: SessionType.MATCH_PREPARATION,
        }
        return _mapping.get(focus, SessionType.MATCH_PREPARATION)

    def _apply_attribute_growth(
        self,
        player: Player,
        attr_increments: dict[str, float],
        base_mult: float,
    ):
        """Apply attribute growth to a player from a set of increments.

        Uses probabilistic rounding: fractional increments are treated as
        a probability of +1. E.g. 0.7 increment = 70% chance of +1.
        """
        potential = player.potential or 50
        overall = player.overall or 50

        for attr_name, base_inc in attr_increments.items():
            # Skip non-attribute entries (work rate boosts, etc.)
            if attr_name.endswith("_boost"):
                continue

            current = getattr(player, attr_name, None)
            if current is None:
                continue
            if current >= 99:
                continue

            # Don't grow much past potential (allow small chance)
            if overall >= potential and random.random() > 0.1:
                continue

            increment = base_inc * base_mult * random.uniform(0.6, 1.4)
            int_part = int(increment)
            frac_part = increment - int_part
            gain = int_part + (1 if random.random() < frac_part else 0)

            if gain > 0:
                new_val = min(99, current + gain)
                setattr(player, attr_name, new_val)

        # Small form boost from training
        player.form = min(100.0, (player.form or 65.0) + random.uniform(0.3, 1.5))

    def _apply_individual_training(
        self,
        player: Player,
        club_id: int,
        coaching_mult: float,
        facility_mult: float,
        age_mult: float,
    ):
        """Apply individual training if the player has one assigned."""
        schedule = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id, player_id=player.id)
            .first()
        )
        if not schedule:
            return
        if not schedule.individual_attrs:
            return

        try:
            target_attrs = json.loads(schedule.individual_attrs)
        except (json.JSONDecodeError, TypeError):
            return

        if not target_attrs:
            return

        try:
            indiv_intensity = TrainingIntensity(schedule.intensity or "normal")
        except ValueError:
            indiv_intensity = TrainingIntensity.NORMAL
        indiv_config = _INTENSITY_CONFIG[indiv_intensity]

        # Individual training gets a bonus increment
        for attr_name in target_attrs:
            current = getattr(player, attr_name, None)
            if current is None or current >= 99:
                continue

            base_inc = 0.4  # individual focus is higher per-attribute
            mult = (
                indiv_config["attr_mult"]
                * coaching_mult
                * facility_mult
                * age_mult
            )
            increment = base_inc * mult * random.uniform(0.5, 1.5)
            int_part = int(increment)
            frac_part = increment - int_part
            gain = int_part + (1 if random.random() < frac_part else 0)

            if gain > 0:
                new_val = min(99, current + gain)
                setattr(player, attr_name, new_val)

    def _tick_individual_schedules(self, club_id: int):
        """Increment weeks_completed on individual schedules and remove finished ones."""
        schedules = (
            self.session.query(TrainingSchedule)
            .filter_by(club_id=club_id)
            .filter(TrainingSchedule.player_id.isnot(None))
            .all()
        )
        for schedule in schedules:
            schedule.weeks_completed = (schedule.weeks_completed or 0) + 1
            if schedule.weeks_completed >= (schedule.duration_weeks or 4):
                self.session.delete(schedule)

    # ── Utility: session descriptions ──────────────────────────────────

    @staticmethod
    def get_session_types() -> list[dict]:
        """Return all session types with their descriptions."""
        result = []
        for st, defn in SESSION_DEFINITIONS.items():
            result.append({
                "type": st.value,
                "name": st.value.replace("_", " ").title(),
                "description": defn.description,
                "fitness_cost": defn.fitness_cost,
                "injury_risk": round(defn.injury_risk * 100, 1),
                "attributes": list(defn.attributes_affected.keys()),
            })
        return result

    @staticmethod
    def get_intensities() -> list[dict]:
        """Return all intensity levels with their effects."""
        result = []
        for intensity, config in _INTENSITY_CONFIG.items():
            result.append({
                "level": intensity.value,
                "name": intensity.value.replace("_", " ").title(),
                "attr_multiplier": config["attr_mult"],
                "fitness_cost": config["fitness_cost"],
                "injury_multiplier": config["injury_mult"],
                "morale_effect": config["morale_boost"],
            })
        return result
