"""Comprehensive player scouting system with progressive knowledge discovery.

Knowledge levels:
    0-20%  : Basic info (name, age, position, nationality, club)
    20-40% : Attribute groups (overall ranges for technical/mental/physical)
    40-60% : Strengths and weaknesses identified
    60-80% : Individual attributes revealed with noise
    80-100%: Full picture — near-accurate attribute values, personality, traits

Scout quality determines the rate of knowledge gain per week.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from fm.db.models import (
    Player, Club, Staff, ScoutAssignment, NewsItem,
)


# ── Attribute labels ───────────────────────────────────────────────────────

_ATTR_LABELS: dict[str, str] = {
    "pace": "Pace",
    "acceleration": "Acceleration",
    "sprint_speed": "Sprint Speed",
    "shooting": "Shooting",
    "finishing": "Finishing",
    "shot_power": "Shot Power",
    "long_shots": "Long Shots",
    "volleys": "Volleys",
    "passing": "Passing",
    "vision": "Vision",
    "crossing": "Crossing",
    "short_passing": "Short Passing",
    "long_passing": "Long Passing",
    "dribbling": "Dribbling",
    "agility": "Agility",
    "balance": "Balance",
    "ball_control": "Ball Control",
    "defending": "Defending",
    "marking": "Marking",
    "standing_tackle": "Standing Tackle",
    "sliding_tackle": "Sliding Tackle",
    "interceptions": "Interceptions",
    "heading_accuracy": "Heading",
    "physical": "Physical",
    "stamina": "Stamina",
    "strength": "Strength",
    "jumping": "Jumping",
    "composure": "Composure",
    "reactions": "Reactions",
    "positioning": "Positioning",
}

_GK_ATTR_LABELS: dict[str, str] = {
    "gk_diving": "Diving",
    "gk_handling": "Handling",
    "gk_kicking": "Kicking",
    "gk_positioning": "GK Positioning",
    "gk_reflexes": "Reflexes",
    "gk_speed": "GK Speed",
}

_MENTAL_ATTRS = [
    "leadership", "teamwork", "determination", "ambition", "loyalty",
    "temperament", "professionalism", "pressure_handling", "composure",
    "flair", "important_matches",
]

_PHYSICAL_ATTRS = [
    "pace", "acceleration", "sprint_speed", "stamina", "strength",
    "jumping", "agility", "balance",
]

_TECHNICAL_ATTRS = [
    "shooting", "finishing", "shot_power", "long_shots", "volleys",
    "passing", "vision", "crossing", "short_passing", "long_passing",
    "dribbling", "ball_control", "curve", "free_kick_accuracy",
    "heading_accuracy",
]

_DEFENDING_ATTRS = [
    "defending", "marking", "standing_tackle", "sliding_tackle", "interceptions",
]

# Attribute groups for progressive reveal at 20-40% knowledge
_ATTRIBUTE_GROUPS = {
    "Technical": _TECHNICAL_ATTRS,
    "Physical": _PHYSICAL_ATTRS,
    "Mental": _MENTAL_ATTRS,
    "Defending": _DEFENDING_ATTRS,
}

# Position group mapping
_POS_GROUP_MAP = {
    "DEF": ["CB", "LB", "RB", "LWB", "RWB"],
    "MID": ["CDM", "CM", "CAM", "LM", "RM"],
    "FWD": ["LW", "RW", "CF", "ST"],
}

# Region -> nationality mapping for region scouting
_REGION_NATIONALITIES: dict[str, list[str]] = {
    "South America": [
        "Brazil", "Argentina", "Colombia", "Uruguay", "Chile",
        "Paraguay", "Ecuador", "Peru", "Venezuela", "Bolivia",
    ],
    "Western Europe": [
        "Spain", "France", "Germany", "Italy", "Portugal",
        "Netherlands", "Belgium", "England", "Scotland", "Wales",
        "Ireland", "Austria", "Switzerland",
    ],
    "Eastern Europe": [
        "Poland", "Czech Republic", "Croatia", "Serbia", "Ukraine",
        "Romania", "Hungary", "Bulgaria", "Slovakia", "Slovenia",
        "Bosnia Herzegovina", "Russia",
    ],
    "Scandinavia": [
        "Sweden", "Norway", "Denmark", "Finland", "Iceland",
    ],
    "Africa": [
        "Nigeria", "Ghana", "Cameroon", "Senegal", "Ivory Coast",
        "Egypt", "Morocco", "Algeria", "Tunisia", "Mali",
        "DR Congo", "Guinea", "South Africa",
    ],
    "Asia": [
        "Japan", "Korea Republic", "China PR", "Australia",
        "Iran", "Saudi Arabia", "India", "Thailand",
    ],
    "North America": [
        "United States", "Mexico", "Canada", "Jamaica", "Costa Rica",
        "Honduras",
    ],
}


# ── Scout Report Data Classes ──────────────────────────────────────────────


@dataclass
class ScoutReport:
    """A scouting report with progressive detail based on knowledge level."""

    player_id: int = 0
    player_name: str = ""
    position: str = ""
    age: int = 0
    nationality: str = ""
    club_name: str = ""

    # Estimates (accuracy improves with knowledge)
    overall_estimate: int = 0
    potential_estimate: int = 0
    estimated_value: float = 0.0       # millions EUR
    wage: float = 0.0

    # Progressive discovery
    knowledge_pct: float = 0.0
    key_strengths: list[str] = field(default_factory=list)
    key_weaknesses: list[str] = field(default_factory=list)
    attribute_groups: dict[str, str] = field(default_factory=dict)
    # e.g. {"Technical": "Very Good (75-85)", "Physical": "Average (55-65)"}
    revealed_attrs: dict[str, int] = field(default_factory=dict)
    # individual attrs with noise based on knowledge
    personality_traits: list[str] = field(default_factory=list)
    player_traits: list[str] = field(default_factory=list)

    # Recommendation
    recommendation: str = ""
    accuracy: float = 0.0             # 0.0-1.0


@dataclass
class RegionScoutResult:
    """Result of region scouting - a discovered player."""
    player_id: int
    player_name: str
    position: str
    age: int
    nationality: str
    club_name: str
    basic_overall_range: str   # e.g. "70-80"


# ── Scouting Manager ──────────────────────────────────────────────────────


class ScoutingManager:
    """Handles player scouting, progressive knowledge, and discovery."""

    def __init__(self, session: DBSession):
        self.session = session

    # ── Assignment management ──────────────────────────────────────────

    def assign_scout_to_player(
        self,
        club_id: int,
        scout_id: int,
        player_id: int,
        season: int,
        matchday: int = 0,
        duration_weeks: int = 4,
    ) -> Optional[ScoutAssignment]:
        """Assign a scout to evaluate a specific player.

        Returns the assignment or None if scout is busy / invalid.
        """
        scout = self.session.get(Staff, scout_id)
        if not scout or scout.club_id != club_id:
            return None
        if scout.role not in ("scout", "chief_scout"):
            return None

        # Check if scout already has an active assignment
        existing = (
            self.session.query(ScoutAssignment)
            .filter_by(scout_id=scout_id, report_ready=False)
            .first()
        )
        if existing:
            return None  # scout is busy

        # Check for existing assignment on this player by this club
        prev = (
            self.session.query(ScoutAssignment)
            .filter_by(club_id=club_id, player_id=player_id, report_ready=True)
            .first()
        )
        start_knowledge = prev.knowledge_pct if prev else 0.0

        assignment = ScoutAssignment(
            scout_id=scout_id,
            player_id=player_id,
            club_id=club_id,
            started_matchday=matchday,
            duration_weeks=duration_weeks,
            weeks_completed=0,
            knowledge_pct=start_knowledge,
            report_ready=False,
            season=season,
        )
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def assign_scout_to_region(
        self,
        club_id: int,
        scout_id: int,
        region: str,
        season: int,
        matchday: int = 0,
        duration_weeks: int = 6,
    ) -> Optional[ScoutAssignment]:
        """Assign a scout to discover players in a region."""
        scout = self.session.get(Staff, scout_id)
        if not scout or scout.club_id != club_id:
            return None

        existing = (
            self.session.query(ScoutAssignment)
            .filter_by(scout_id=scout_id, report_ready=False)
            .first()
        )
        if existing:
            return None

        assignment = ScoutAssignment(
            scout_id=scout_id,
            club_id=club_id,
            region=region,
            started_matchday=matchday,
            duration_weeks=duration_weeks,
            weeks_completed=0,
            knowledge_pct=0.0,
            report_ready=False,
            season=season,
        )
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def assign_scout_to_club(
        self,
        club_id: int,
        scout_id: int,
        target_club_id: int,
        season: int,
        matchday: int = 0,
        duration_weeks: int = 4,
    ) -> Optional[ScoutAssignment]:
        """Assign a scout to evaluate all players at a target club."""
        scout = self.session.get(Staff, scout_id)
        if not scout or scout.club_id != club_id:
            return None

        existing = (
            self.session.query(ScoutAssignment)
            .filter_by(scout_id=scout_id, report_ready=False)
            .first()
        )
        if existing:
            return None

        assignment = ScoutAssignment(
            scout_id=scout_id,
            club_id=club_id,
            target_club_id=target_club_id,
            started_matchday=matchday,
            duration_weeks=duration_weeks,
            weeks_completed=0,
            knowledge_pct=0.0,
            report_ready=False,
            season=season,
        )
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def cancel_assignment(self, assignment_id: int, club_id: int) -> bool:
        """Cancel an active scouting assignment."""
        assignment = self.session.get(ScoutAssignment, assignment_id)
        if not assignment or assignment.club_id != club_id:
            return False
        self.session.delete(assignment)
        self.session.flush()
        return True

    def get_active_assignments(self, club_id: int) -> list[ScoutAssignment]:
        """Return all active (incomplete) assignments for a club."""
        return (
            self.session.query(ScoutAssignment)
            .filter_by(club_id=club_id, report_ready=False)
            .all()
        )

    def get_completed_reports(self, club_id: int) -> list[ScoutAssignment]:
        """Return all completed assignments for a club."""
        return (
            self.session.query(ScoutAssignment)
            .filter_by(club_id=club_id, report_ready=True)
            .order_by(ScoutAssignment.knowledge_pct.desc())
            .all()
        )

    def get_available_scouts(self, club_id: int) -> list[Staff]:
        """Return scouts not currently on assignment."""
        busy_ids = {
            a.scout_id for a in
            self.session.query(ScoutAssignment.scout_id)
            .filter_by(club_id=club_id, report_ready=False)
            .all()
        }
        all_scouts = (
            self.session.query(Staff)
            .filter(
                Staff.club_id == club_id,
                Staff.role.in_(["scout", "chief_scout"]),
            )
            .all()
        )
        return [s for s in all_scouts if s.id not in busy_ids]

    # ── Weekly processing ──────────────────────────────────────────────

    def process_weekly(self, club_id: int, season: int, matchday: int = 0):
        """Process all active scouting assignments for one week.

        Knowledge gain per week depends on:
        - Scout's scouting_ability (1-99)
        - Club's scouting_network_level (1-10)
        - Whether scouting a player, club, or region
        """
        club = self.session.get(Club, club_id)
        network_level = club.scouting_network_level if club else 3

        assignments = self.get_active_assignments(club_id)

        for assignment in assignments:
            scout = self.session.get(Staff, assignment.scout_id)
            if not scout:
                continue

            scout_ability = scout.scouting_ability or 50
            # Base knowledge gain: 10-25% per week depending on scout quality
            base_gain = 10.0 + (scout_ability / 99.0) * 15.0
            # Network bonus: 0.8x to 1.4x
            network_mult = 0.8 + (network_level - 1) * (0.6 / 9.0)
            # Randomness
            knowledge_gain = base_gain * network_mult * random.uniform(0.7, 1.3)

            # Region scouting is slower (wider scope)
            if assignment.region:
                knowledge_gain *= 0.5
            # Club scouting is moderately paced
            elif assignment.target_club_id:
                knowledge_gain *= 0.7

            assignment.knowledge_pct = min(
                100.0, (assignment.knowledge_pct or 0.0) + knowledge_gain,
            )
            assignment.weeks_completed = (assignment.weeks_completed or 0) + 1

            # Check if assignment is complete
            is_done = (
                assignment.weeks_completed >= (assignment.duration_weeks or 4)
                or assignment.knowledge_pct >= 100.0
            )
            if is_done:
                assignment.report_ready = True

                # Generate news for completed reports
                if assignment.player_id:
                    player = self.session.get(Player, assignment.player_id)
                    pname = player.name if player else "Unknown"
                    self.session.add(NewsItem(
                        season=season,
                        matchday=matchday,
                        headline=f"Scout report completed on {pname}",
                        body=(
                            f"{scout.name} has completed a scouting report on {pname}. "
                            f"Knowledge: {assignment.knowledge_pct:.0f}%."
                        ),
                        category="general",
                    ))
                elif assignment.region:
                    self.session.add(NewsItem(
                        season=season,
                        matchday=matchday,
                        headline=f"Regional scouting report: {assignment.region}",
                        body=(
                            f"{scout.name} has completed scouting in {assignment.region}."
                        ),
                        category="general",
                    ))
                elif assignment.target_club_id:
                    tclub = self.session.get(Club, assignment.target_club_id)
                    cname = tclub.name if tclub else "Unknown"
                    self.session.add(NewsItem(
                        season=season,
                        matchday=matchday,
                        headline=f"Club scouting report: {cname}",
                        body=(
                            f"{scout.name} has completed scouting {cname}."
                        ),
                        category="general",
                    ))

        self.session.flush()

    # ── Report generation ──────────────────────────────────────────────

    def scout_player(
        self,
        player_id: int,
        scout_quality: int = 50,
        squad_avg: float | None = None,
        knowledge_pct: float | None = None,
    ) -> Optional[ScoutReport]:
        """Generate a scout report on a player.

        If knowledge_pct is not provided, uses scout_quality to derive
        an instant accuracy (backward-compatible quick scout).
        """
        player = self.session.get(Player, player_id)
        if not player:
            return None

        # Determine knowledge level
        if knowledge_pct is not None:
            knowledge = min(100.0, max(0.0, knowledge_pct))
        else:
            # Instant scout: quality maps to ~30-80% knowledge
            knowledge = 30.0 + (scout_quality / 99.0) * 50.0

        accuracy = knowledge / 100.0

        # Club info
        club = None
        if player.club_id:
            club = self.session.get(Club, player.club_id)
        club_name = club.name if club else "Free Agent"

        report = ScoutReport(
            player_id=player.id,
            player_name=player.short_name or player.name,
            position=player.position or "?",
            age=player.age or 25,
            nationality=player.nationality or "Unknown",
            club_name=club_name,
            knowledge_pct=round(knowledge, 1),
            accuracy=round(accuracy, 2),
            wage=player.wage or 0.0,
        )

        # ── Level 1: Basic info (always available) ──
        # Name, age, position, nationality, club are in the report already.

        # ── Overall / potential estimates (noise decreases with knowledge) ──
        ovr_noise = int((1.0 - accuracy) * 12)
        pot_noise = int((1.0 - accuracy) * 20)
        ovr_delta = random.randint(-ovr_noise, ovr_noise) if ovr_noise else 0
        pot_delta = random.randint(-pot_noise, pot_noise) if pot_noise else 0
        report.overall_estimate = max(1, min(99, (player.overall or 50) + ovr_delta))
        report.potential_estimate = max(1, min(99, (player.potential or 50) + pot_delta))

        # ── Value estimate ──
        real_value = self._estimate_market_value(player)
        val_noise = random.uniform(
            1.0 - (1.0 - accuracy) * 0.35,
            1.0 + (1.0 - accuracy) * 0.35,
        )
        report.estimated_value = round(max(0.05, real_value * val_noise), 2)

        # ── Level 2: Attribute groups (20%+) ──
        if knowledge >= 20.0:
            report.attribute_groups = self._get_attribute_group_ranges(player, accuracy)

        # ── Level 3: Strengths / weaknesses (40%+) ──
        if knowledge >= 40.0:
            report.key_strengths, report.key_weaknesses = (
                self._get_strengths_weaknesses(player, accuracy)
            )

        # ── Level 4: Individual attributes (60%+) ──
        if knowledge >= 60.0:
            report.revealed_attrs = self._get_revealed_attrs(player, accuracy)

        # ── Level 5: Full picture (80%+) ──
        if knowledge >= 80.0:
            report.personality_traits = self._get_personality_summary(player)
            if player.traits:
                try:
                    report.player_traits = json.loads(player.traits)
                except (json.JSONDecodeError, TypeError):
                    pass

        # ── Recommendation ──
        report.recommendation = self._generate_recommendation(
            player, report.overall_estimate, report.potential_estimate,
            report.estimated_value, squad_avg,
        )

        return report

    def get_report_for_assignment(
        self,
        assignment_id: int,
        squad_avg: float | None = None,
    ) -> Optional[ScoutReport]:
        """Generate a report from a completed assignment."""
        assignment = self.session.get(ScoutAssignment, assignment_id)
        if not assignment or not assignment.player_id:
            return None

        scout = self.session.get(Staff, assignment.scout_id)
        scout_quality = scout.scouting_ability if scout else 50

        return self.scout_player(
            assignment.player_id,
            scout_quality=scout_quality,
            squad_avg=squad_avg,
            knowledge_pct=assignment.knowledge_pct,
        )

    def get_region_discoveries(
        self,
        assignment_id: int,
    ) -> list[RegionScoutResult]:
        """Get players discovered from a region scouting assignment."""
        assignment = self.session.get(ScoutAssignment, assignment_id)
        if not assignment or not assignment.region:
            return []

        region = assignment.region
        nationalities = _REGION_NATIONALITIES.get(region, [])
        if not nationalities:
            return []

        scout = self.session.get(Staff, assignment.scout_id)
        scout_ability = scout.scouting_ability if scout else 50

        # Number of players discovered depends on knowledge and ability
        knowledge = assignment.knowledge_pct or 0.0
        base_count = 3 + int(knowledge / 20.0)  # 3-8 players
        ability_bonus = int(scout_ability / 33.0)  # 0-3
        total_discover = min(base_count + ability_bonus, 15)

        # Query matching players
        candidates = (
            self.session.query(Player)
            .filter(Player.nationality.in_(nationalities))
            .filter(Player.overall >= 55)  # minimum quality filter
            .order_by(Player.overall.desc())
            .limit(total_discover * 3)  # over-fetch for randomness
            .all()
        )

        if not candidates:
            return []

        # Weighted random selection (better scouts find better players)
        selected = random.sample(
            candidates, min(total_discover, len(candidates)),
        )

        results = []
        for p in selected:
            ovr = p.overall or 50
            noise = random.randint(-8, 8)
            low = max(1, ovr + noise - 5)
            high = min(99, ovr + noise + 5)

            club = self.session.get(Club, p.club_id) if p.club_id else None
            results.append(RegionScoutResult(
                player_id=p.id,
                player_name=p.short_name or p.name,
                position=p.position or "?",
                age=p.age or 25,
                nationality=p.nationality or "Unknown",
                club_name=club.name if club else "Free Agent",
                basic_overall_range=f"{low}-{high}",
            ))

        return results

    def get_club_scouting_results(
        self,
        assignment_id: int,
        squad_avg: float | None = None,
    ) -> list[ScoutReport]:
        """Get reports for all players at a scouted club."""
        assignment = self.session.get(ScoutAssignment, assignment_id)
        if not assignment or not assignment.target_club_id:
            return []

        players = (
            self.session.query(Player)
            .filter_by(club_id=assignment.target_club_id)
            .order_by(Player.overall.desc())
            .all()
        )

        scout = self.session.get(Staff, assignment.scout_id)
        scout_quality = scout.scouting_ability if scout else 50
        knowledge = assignment.knowledge_pct or 0.0

        reports = []
        for p in players:
            report = self.scout_player(
                p.id,
                scout_quality=scout_quality,
                squad_avg=squad_avg,
                knowledge_pct=knowledge * 0.8,  # slightly less per-player than single scout
            )
            if report:
                reports.append(report)

        return reports

    # ── Search methods (backward compatible) ───────────────────────────

    def search_wonderkids(
        self,
        max_age: int = 21,
        min_potential: int = 80,
        max_results: int = 20,
        scout_quality: int = 50,
        squad_avg: float | None = None,
    ) -> list[ScoutReport]:
        """Find young high-potential players."""
        players = (
            self.session.query(Player)
            .filter(Player.age <= max_age, Player.potential >= min_potential)
            .order_by(Player.potential.desc())
            .limit(max_results)
            .all()
        )
        return [
            r for p in players
            if (r := self.scout_player(p.id, scout_quality, squad_avg)) is not None
        ]

    def search_bargains(
        self,
        max_value: float = 5.0,
        min_overall: int = 70,
        max_results: int = 20,
        scout_quality: int = 50,
        squad_avg: float | None = None,
    ) -> list[ScoutReport]:
        """Find undervalued players."""
        players = (
            self.session.query(Player)
            .filter(
                Player.overall >= min_overall,
                Player.market_value <= max_value,
                Player.market_value > 0,
            )
            .order_by(Player.overall.desc())
            .limit(max_results)
            .all()
        )
        return [
            r for p in players
            if (r := self.scout_player(p.id, scout_quality, squad_avg)) is not None
        ]

    def search_free_agents(
        self,
        min_overall: int = 60,
        max_results: int = 20,
        scout_quality: int = 50,
        squad_avg: float | None = None,
    ) -> list[ScoutReport]:
        """Find free agents worth signing."""
        players = (
            self.session.query(Player)
            .filter(Player.club_id.is_(None), Player.overall >= min_overall)
            .order_by(Player.overall.desc())
            .limit(max_results)
            .all()
        )
        return [
            r for p in players
            if (r := self.scout_player(p.id, scout_quality, squad_avg)) is not None
        ]

    def search_by_position(
        self,
        position: str,
        min_overall: int = 60,
        max_results: int = 20,
        scout_quality: int = 50,
        squad_avg: float | None = None,
    ) -> list[ScoutReport]:
        """Search for players by position."""
        q = self.session.query(Player).filter(Player.overall >= min_overall)
        if position in _POS_GROUP_MAP:
            q = q.filter(Player.position.in_(_POS_GROUP_MAP[position]))
        else:
            q = q.filter(Player.position == position)
        players = q.order_by(Player.overall.desc()).limit(max_results).all()
        return [
            r for p in players
            if (r := self.scout_player(p.id, scout_quality, squad_avg)) is not None
        ]

    def get_position_report(self, club_id: int, position: str) -> dict:
        """Compare available targets for a position with current players."""
        if position in _POS_GROUP_MAP:
            positions = _POS_GROUP_MAP[position]
        else:
            positions = [position]

        current_players = (
            self.session.query(Player)
            .filter(Player.club_id == club_id, Player.position.in_(positions))
            .order_by(Player.overall.desc())
            .all()
        )

        squad_avg = (
            sum(p.overall or 0 for p in current_players) / max(len(current_players), 1)
        )

        current_reports = [
            r for p in current_players
            if (r := self.scout_player(p.id, scout_quality=99, squad_avg=squad_avg))
            is not None
        ]

        targets_q = (
            self.session.query(Player)
            .filter(
                Player.club_id != club_id,
                Player.position.in_(positions),
                Player.overall >= max(int(squad_avg) - 10, 50),
            )
            .order_by(Player.overall.desc())
            .limit(20)
        )
        target_players = targets_q.all()

        target_reports = [
            r for p in target_players
            if (r := self.scout_player(p.id, scout_quality=70, squad_avg=squad_avg))
            is not None
        ]

        return {
            "current": current_reports,
            "targets": target_reports,
            "position": position,
            "squad_avg_at_pos": round(squad_avg, 1),
        }

    # ── Internal helpers ───────────────────────────────────────────────

    def _estimate_market_value(self, player: Player) -> float:
        """Estimate market value in millions (simple formula)."""
        ovr = player.overall or 50
        pot = player.potential or 50
        age = player.age or 25

        # Base value from overall
        if ovr >= 85:
            base = 40.0 + (ovr - 85) * 8.0
        elif ovr >= 75:
            base = 10.0 + (ovr - 75) * 3.0
        elif ovr >= 65:
            base = 2.0 + (ovr - 65) * 0.8
        else:
            base = max(0.1, ovr * 0.03)

        # Age factor
        if age <= 23:
            age_mult = 1.3 + (23 - age) * 0.1
        elif age <= 28:
            age_mult = 1.0
        elif age <= 32:
            age_mult = 0.7 - (age - 28) * 0.1
        else:
            age_mult = max(0.1, 0.3 - (age - 32) * 0.05)

        # Potential premium for young players
        pot_bonus = 0.0
        if age <= 24 and pot > ovr:
            pot_bonus = (pot - ovr) * 0.5

        return max(0.05, (base + pot_bonus) * age_mult)

    def _get_attribute_group_ranges(
        self, player: Player, accuracy: float,
    ) -> dict[str, str]:
        """Return attribute group summaries with accuracy-based ranges."""
        result = {}
        for group_name, attrs in _ATTRIBUTE_GROUPS.items():
            values = [
                getattr(player, a, 50) or 50
                for a in attrs
                if hasattr(player, a)
            ]
            if not values:
                continue
            avg = sum(values) / len(values)
            noise = int((1.0 - accuracy) * 10)
            low = max(1, int(avg) - noise - 3)
            high = min(99, int(avg) + noise + 3)

            label = self._quality_label(avg)
            result[group_name] = f"{label} ({low}-{high})"

        return result

    @staticmethod
    def _quality_label(value: float) -> str:
        """Convert numeric value to a quality label."""
        if value >= 85:
            return "World Class"
        elif value >= 75:
            return "Very Good"
        elif value >= 65:
            return "Good"
        elif value >= 55:
            return "Average"
        elif value >= 45:
            return "Below Average"
        else:
            return "Poor"

    def _get_strengths_weaknesses(
        self, player: Player, accuracy: float,
    ) -> tuple[list[str], list[str]]:
        """Identify top strengths and weaknesses."""
        attr_map = _GK_ATTR_LABELS if player.position == "GK" else _ATTR_LABELS
        attr_values = {}
        for attr_name, label in attr_map.items():
            val = getattr(player, attr_name, None)
            if val is not None:
                # Add slight noise inversely proportional to accuracy
                noise = random.randint(
                    -int((1.0 - accuracy) * 5),
                    int((1.0 - accuracy) * 5),
                ) if accuracy < 0.9 else 0
                attr_values[label] = val + noise

        sorted_desc = sorted(attr_values.items(), key=lambda x: x[1], reverse=True)
        strengths = [
            f"{label} ({max(1, min(99, val))})"
            for label, val in sorted_desc if val >= 75
        ][:4]

        sorted_asc = sorted(attr_values.items(), key=lambda x: x[1])
        weaknesses = [
            f"{label} ({max(1, min(99, val))})"
            for label, val in sorted_asc if val < 50
        ][:4]

        return strengths, weaknesses

    def _get_revealed_attrs(
        self, player: Player, accuracy: float,
    ) -> dict[str, int]:
        """Return individual attribute values with noise based on accuracy."""
        attr_map = _GK_ATTR_LABELS if player.position == "GK" else _ATTR_LABELS
        revealed = {}
        noise_range = max(0, int((1.0 - accuracy) * 8))

        for attr_name, label in attr_map.items():
            val = getattr(player, attr_name, None)
            if val is None:
                continue
            noise = random.randint(-noise_range, noise_range) if noise_range else 0
            revealed[attr_name] = max(1, min(99, val + noise))

        return revealed

    def _get_personality_summary(self, player: Player) -> list[str]:
        """Derive personality trait labels from mental attributes."""
        traits = []
        if (player.determination or 50) >= 75:
            traits.append("Determined")
        if (player.professionalism or 50) >= 75:
            traits.append("Professional")
        if (player.ambition or 50) >= 75:
            traits.append("Ambitious")
        if (player.loyalty or 50) >= 75:
            traits.append("Loyal")
        if (player.leadership or 50) >= 75:
            traits.append("Born Leader")
        if (player.temperament or 50) < 35:
            traits.append("Volatile")
        if (player.pressure_handling or 50) >= 75:
            traits.append("Thrives Under Pressure")
        if (player.flair or 50) >= 80:
            traits.append("Flair Player")
        if (player.teamwork or 50) >= 75:
            traits.append("Team Player")
        if (player.professionalism or 50) < 35:
            traits.append("Unprofessional")
        if (player.determination or 50) < 35:
            traits.append("Lacks Drive")
        if (player.adaptability or 50) >= 75:
            traits.append("Adaptable")

        return traits[:6]

    def _generate_recommendation(
        self,
        player: Player,
        overall_est: int,
        potential_est: int,
        value_est: float,
        squad_avg: float | None,
    ) -> str:
        """Generate a recommendation string based on player evaluation."""
        age = player.age or 25
        ovr = overall_est
        pot = potential_est
        value_per_ovr = value_est / max(ovr, 1)
        is_bargain = value_per_ovr < 0.15

        if age <= 21 and pot >= 85:
            return "Generational talent - sign immediately!"
        if age <= 21 and pot >= 80:
            return "Exceptional prospect - sign immediately"
        if age <= 23 and pot >= 75 and pot - ovr >= 10:
            return "High potential - great investment"

        if squad_avg is not None:
            diff = ovr - squad_avg
            if diff >= 10:
                return "Sign immediately - major upgrade"
            elif diff >= 5:
                return "Strong signing - clear improvement"
            elif diff >= 0:
                return "Good backup option"
            elif diff >= -5:
                return "Marginal - squad depth only"
            else:
                return "Not worth it - below squad level"

        if ovr >= 85:
            return "World class - sign if affordable"
        if ovr >= 80 and age <= 28:
            return "Strong signing - prime years"
        if ovr >= 75 and is_bargain:
            return "Bargain buy - good value"
        if ovr >= 70:
            return "Decent option - solid squad player"
        if age >= 32:
            return "Veteran - short-term option only"
        if ovr < 65:
            return "Not worth it - too low quality"

        return "Average prospect - consider alternatives"
