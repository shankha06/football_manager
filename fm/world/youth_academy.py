"""Youth academy system: intake generation, development, and promotion.

Generates annual youth intakes based on club academy level,
develops candidates over time, and promotes them to the first team
by converting YouthCandidate rows into Player rows.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from fm.db.models import Club, Player, YouthCandidate, NewsItem


# ── National Youth Ratings (Baseline Talent Pool) ──────────────────────────
# Looks little overpowered. validate well and then tune the numbers.

NATIONAL_YOUTH_RATINGS = {
    "Brazil": 163,
    "France": 155,
    "Germany": 155,
    "Spain": 145,
    "Italy": 144,
    "Argentina": 140,
    "England": 135,
    "Portugal": 134,
    "Netherlands": 132,
    "Turkey": 125,
    "Scotland": 110,
    "USA": 100,
}

# ── Name generation pools by Region ─────────────────────────────────────────

REGIONAL_NAMES = {
    "british_isles": {  # England, Scotland, etc.
        "first": ["James", "Jack", "Harry", "Oliver", "George", "Noah", "Leo", "Oscar", "Finn", "Liam", "Callum", "Ewan"],
        "last": ["Smith", "Jones", "Williams", "Brown", "Taylor", "Wilson", "Davies", "Evans", "Campbell", "Stewart", "Murray"]
    },
    "western_europe": {  # France, Germany, Netherlands
        "first": ["Lucas", "Matteo", "Hugo", "Leo", "Noah", "Gabriel", "Rayan", "Finn", "Jonas", "Niklas", "Artem", "Sandro"],
        "last": ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Martin", "Bernard", "Dubois", "Robert", "De Jong", "Van Dijk"]
    },
    "southern_europe": {  # Spain, Italy, Portugal
        "first": ["Mateo", "Alex", "Daniel", "Gabriel", "Luis", "Tiago", "Marco", "Lorenzo", "Enzo", "Luca", "Rafael", "Cristian", "Diego", "Pablo"],
        "last": ["Garcia", "Rodriguez", "Martinez", "Lopez", "Hernandez", "Gonzalez", "Silva", "Santos", "Oliveira", "Costa", "Rossi", "Russo", "Ferrari"]
    },
    "middle_east": {  # Turkey
        "first": ["Emre", "Arda", "Can", "Burak", "Kerem", "Yusuf", "Hakan", "Mert", "Ozan", "Taha", "Eray"],
        "last": ["Yilmaz", "Demir", "Kaya", "Celik", "Sahin", "Aydin", "Ozdemir", "Arslan", "Dogan", "Kilic"]
    },
    "north_america": {  # USA
        "first": ["Liam", "Noah", "Oliver", "Ethan", "Aiden", "Jackson", "Logan", "Mason", "Lucas", "Christian", "Tyler", "Jordan"],
        "last": ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Perez"]
    },
    "south_america": {  # Brazil, Argentina
        "first": ["Gabriel", "Lucas", "Mateo", "Rafael", "Diego", "Pablo", "Enzo", "Nicolas", "Thiago", "Vinicius", "Vitor"],
        "last": ["Silva", "Santos", "Souza", "Oliveira", "Pereira", "Costa", "Rodriguez", "Gonzalez", "Hernandez", "Fernandez"]
    },
    "scandinavia": {  # Sweden, Denmark, Norway
        "first": ["Erik", "Anders", "Lukas", "Niklas", "Jonas", "Filip", "Viktor", "Oscar", "Magnus", "Frederik"],
        "last": ["Andersson", "Johansson", "Eriksson", "Larsson", "Nilsson", "Jensen", "Nielsen", "Hansen", "Pedersen"]
    },
    "eastern_europe": {  # Poland, Russia, etc.
        "first": ["Artem", "Filip", "Viktor", "Arkadij", "Lukasz", "Marek", "Piotr", "Tomasz", "Jan", "Krzysztof"],
        "last": ["Nowak", "Kowalski", "Novak", "Horvat", "Popovic", "Jankowski", "Wojcik", "Kaminski"]
    },
    "africa": {  # Nigeria, Ghana, Senegal
        "first": ["Kwame", "Kofi", "Moussa", "Cheikh", "Abdou", "Ousmane", "Ibrahim", "Samuel", "Emmanuel", "Victor"],
        "last": ["Diallo", "Traore", "Mensah", "Okafor", "Diop", "Cisse", "Sane", "Gaye", "Toure"]
    },
    "asia": {  # Japan, Korea, China
        "first": ["Hiroto", "Ren", "Yuma", "Min-ho", "Ji-hoon", "Wei", "Jun", "Ken", "Sho", "Taro"],
        "last": ["Tanaka", "Suzuki", "Sato", "Kim", "Lee", "Park", "Li", "Zhang", "Wang", "Watanabe"]
    }
}

COUNTRY_TO_REGION = {
    "England": "british_isles", "Scotland": "british_isles", "Wales": "british_isles", "Ireland": "british_isles",
    "France": "western_europe", "Germany": "western_europe", "Netherlands": "western_europe", "Belgium": "western_europe",
    "Spain": "southern_europe", "Italy": "southern_europe", "Portugal": "southern_europe",
    "Turkey": "middle_east", "USA": "north_america", "Canada": "north_america",
    "Brazil": "south_america", "Argentina": "south_america", "Uruguay": "south_america",
    "Sweden": "scandinavia", "Denmark": "scandinavia", "Norway": "scandinavia",
    "Poland": "eastern_europe", "Russia": "eastern_europe", "Czech Republic": "eastern_europe",
    "Nigeria": "africa", "Ghana": "africa", "Senegal": "africa", "Ivory Coast": "africa",
    "Japan": "asia", "South Korea": "asia", "China": "asia",
}

# ── Archetype Profiles (Attribute Weightings) ──────────────────────────────

ARCHETYPE_PROFILES = {
    "goalkeeper": {"gk_diving": 1.2, "gk_handling": 1.1, "gk_reflexes": 1.1, "gk_positioning": 1.1},
    "sweeper_keeper": {"gk_reflexes": 1.2, "gk_speed": 1.2, "gk_kicking": 1.1, "passing": 0.9, "acceleration": 0.8},
    "central_defender": {"defending": 1.2, "marking": 1.2, "standing_tackle": 1.1, "heading_accuracy": 1.1, "strength": 1.1, "jumping": 1.1},
    "ball_playing_defender": {"defending": 1.0, "passing": 1.1, "long_passing": 1.1, "vision": 0.9, "composed": 1.0, "ball_control": 0.9},
    "no_nonsense_defender": {"defending": 1.3, "strength": 1.2, "aggression": 1.1, "heading_accuracy": 1.1, "marking": 1.1, "pace": 0.6},
    "full_back": {"pace": 1.1, "acceleration": 1.1, "stamina": 1.2, "defending": 1.0, "crossing": 0.9, "marking": 1.0},
    "wing_back": {"pace": 1.2, "acceleration": 1.2, "stamina": 1.3, "crossing": 1.1, "dribbling": 1.0, "defending": 0.8},
    "anchor_man": {"defending": 1.2, "interceptions": 1.2, "positioning": 1.2, "strength": 1.1, "teamwork": 1.1, "pace": 0.7},
    "regista": {"passing": 1.3, "vision": 1.3, "short_passing": 1.2, "long_passing": 1.2, "ball_control": 1.1, "defending": 0.6},
    "box_to_box": {"stamina": 1.4, "work_rate": 1.3, "passing": 1.0, "finishing": 0.8, "strength": 1.0, "defending": 0.9},
    "mezzala": {"passing": 1.1, "vision": 1.1, "dribbling": 1.1, "agility": 1.1, "finishing": 0.9, "acceleration": 1.0},
    "advanced_playmaker": {"vision": 1.4, "passing": 1.3, "ball_control": 1.2, "short_passing": 1.2, "dribbling": 1.1, "composure": 1.1},
    "trequartista": {"vision": 1.3, "flair": 1.4, "finishing": 1.0, "passing": 1.1, "dribbling": 1.2, "stamina": 0.6},
    "shadow_striker": {"finishing": 1.2, "off_the_ball": 1.2, "composure": 1.1, "passing": 0.9, "pace": 1.1, "aggression": 1.0},
    "winger": {"pace": 1.4, "acceleration": 1.4, "dribbling": 1.3, "crossing": 1.3, "agility": 1.2, "stamina": 1.1},
    "inside_forward": {"finishing": 1.2, "dribbling": 1.2, "pace": 1.3, "acceleration": 1.3, "agility": 1.1, "shooting": 1.1},
    "inverted_winger": {"dribbling": 1.3, "vision": 1.1, "passing": 1.1, "crossing": 1.0, "agility": 1.2, "finishing": 0.9},
    "target_man": {"strength": 1.4, "heading_accuracy": 1.4, "jumping": 1.3, "balance": 1.2, "aggression": 1.1, "pace": 0.6},
    "poacher": {"finishing": 1.4, "off_the_ball": 1.4, "acceleration": 1.3, "composure": 1.2, "shooting": 1.1, "strength": 0.7},
    "advanced_forward": {"finishing": 1.2, "pace": 1.3, "acceleration": 1.3, "dribbling": 1.1, "stamina": 1.1, "composure": 1.0},
    "pressing_forward": {"stamina": 1.4, "aggression": 1.4, "work_rate": 1.4, "courage": 1.2, "determination": 1.2, "finishing": 0.9},
}

_POSITIONS = ["GK", "CB", "LB", "RB", "CDM", "CM", "CAM", "LW", "RW", "ST"]

_POSITION_WEIGHTS = {
    "GK": 1, "CB": 3, "LB": 2, "RB": 2,
    "CDM": 2, "CM": 3, "CAM": 2,
    "LW": 2, "RW": 2, "ST": 3,
}

_PERSONALITY_TYPES = [
    "balanced", "determined", "professional", "lazy", "volatile",
    "perfectionist", "spirited", "casual", "ambitious",
]

_PERSONALITY_WEIGHTS = [25, 15, 15, 5, 5, 10, 10, 5, 10]


# ── Helper: weighted position choice ──────────────────────────────────────

def _weighted_position() -> str:
    positions = list(_POSITION_WEIGHTS.keys())
    weights = list(_POSITION_WEIGHTS.values())
    return random.choices(positions, weights=weights, k=1)[0]


def _generate_name(country: str | None = None) -> str:
    region = "british_isles"
    if country and country in COUNTRY_TO_REGION:
        region = COUNTRY_TO_REGION[country]

    pool = REGIONAL_NAMES.get(region, REGIONAL_NAMES["british_isles"])
    first = random.choice(pool["first"])
    last = random.choice(pool["last"])
    return f"{first} {last}"


# ── Personality growth modifiers ───────────────────────────────────────────

_PERSONALITY_GROWTH_MULT: dict[str, float] = {
    "determined": 1.3,
    "professional": 1.2,
    "perfectionist": 1.25,
    "ambitious": 1.15,
    "spirited": 1.1,
    "balanced": 1.0,
    "casual": 0.85,
    "lazy": 0.7,
    "volatile": 0.9,
}


# ── Youth Academy Manager ─────────────────────────────────────────────────


class YouthAcademyManager:
    """Manages the youth academy: intake, development, and promotion."""

    def __init__(self, session: DBSession):
        self.session = session

    # ── Annual youth intake ────────────────────────────────────────────

    def generate_youth_intake(
        self,
        club_id: int,
        season_year: int,
        matchday: int | None = None,
        override_count: int | None = None,
    ) -> list[YouthCandidate]:
        """Generate the annual youth intake for a club.

        Number/Quality depends on:
        - Club.youth_academy_level
        - Staff (youth_coach) skills
        - Manager.youth_development skill
        - National Youth Rating (baseline talent)
        """
        from fm.db.models import Staff, Manager, League

        club = self.session.get(Club, club_id)
        if not club:
            return []

        # 1. Get Quality Modifiers
        academy_level = club.youth_academy_level or 5
        scouting_level = club.scouting_network_level or 3

        # Staff influence (Youth Coach)
        youth_coach = self.session.query(Staff).filter_by(club_id=club_id, role="youth_coach").first()
        coach_bonus = (youth_coach.coaching_mental + youth_coach.coaching_technical) / 100.0 if youth_coach else 0.5

        # Manager influence
        manager = self.session.query(Manager).filter_by(club_id=club_id).first()
        manager_bonus = (manager.youth_development / 100.0) if manager else 0.5

        # National Baseline
        league = self.session.get(League, club.league_id) if club.league_id else None
        country = league.country if league else "England"
        nat_rating = NATIONAL_YOUTH_RATINGS.get(country, 100)
        nat_mult = nat_rating / 135.0  # Normalized to England (135)

        # 2. Intake Size
        if override_count is not None:
            count = override_count
        else:
            min_count = max(3, academy_level - 2)
            max_count = min(15, academy_level + 5)
            count = random.randint(min_count, max_count)

        # 3. Golden Generation?
        is_golden = random.random() < 0.03  # 3% chance

        # 4. Global Potential Ranges
        # Base starts from level, modified by coaches and national pool
        pot_base = 40 + (academy_level * 3) + (coach_bonus * 5) + (manager_bonus * 5)
        pot_base *= nat_mult

        candidates = []
        for _ in range(count):
            # A. Position
            position = _weighted_position()

            # B. Archetype
            from fm.config import PLAYER_ROLES
            roles = PLAYER_ROLES.get(position, ["central_midfielder"])
            archetype = random.choice(roles)

            # C. Personality & Hidden traits
            personality = random.choices(
                _PERSONALITY_TYPES, weights=_PERSONALITY_WEIGHTS, k=1,
            )[0]

            # Generate hidden attributes (1-99)
            # Base logic: Better academies produce slightly more professional/ambitious players
            base_hidden = 35 + (academy_level * 3) + random.randint(-15, 15)

            # Personality specific boosts
            determination = min(99, max(1, base_hidden + (20 if personality == "determined" else 0)))
            professionalism = min(99, max(1, base_hidden + (20 if personality == "professional" else 0)))
            ambition = min(99, max(1, base_hidden + random.randint(-10, 20)))
            loyalty = min(99, max(1, 50 + random.randint(-20, 30)))
            pressure = min(99, max(1, base_hidden + random.randint(-20, 20)))
            consistency = min(99, max(1, base_hidden + random.randint(-20, 10)))
            injury_prone = random.randint(1, 60) # lower is better, usually
            important_matches = min(99, max(1, base_hidden + random.randint(-15, 15)))

            # D. Nationality Variation
            # Chance to find foreign talent based on scouting level
            cand_nat = country
            if random.random() < (scouting_level * 0.02):
                # Pick a random scouting region
                from fm.config import SCOUTING_REGIONS
                cand_nat = random.choice(SCOUTING_REGIONS)
                # Filter out generic region names if they appear
                if cand_nat in ["South America", "Africa", "Eastern Europe", "Scandinavia"]:
                    # Mapping generic to a representative country if needed
                    nat_map = {"South America": "Brazil", "Africa": "Nigeria", "Scandinavia": "Denmark"}
                    cand_nat = nat_map.get(cand_nat, "France")

            # E. CA / PA Logic
            # Individual variance
            variance = random.randint(-10, 15)
            if is_golden:
                variance += random.randint(10, 25)

            pot_max = min(99, int(pot_base + variance + random.randint(5, 15)))
            pot_min = max(30, pot_max - random.randint(15, 30))

            ca = max(15, pot_min - random.randint(15, 30))

            # Age: 15-17
            age = random.choices([15, 16, 17], weights=[20, 50, 30], k=1)[0]
            name = _generate_name(cand_nat)

            candidate = YouthCandidate(
                club_id=club_id,
                name=name,
                age=age,
                position=position,
                nationality=cand_nat,
                archetype=archetype,
                potential_min=pot_min,
                potential_max=pot_max,
                current_ability=ca,
                personality_type=personality,
                determination=determination,
                professionalism=professionalism,
                ambition=ambition,
                loyalty=loyalty,
                pressure=pressure,
                consistency=consistency,
                injury_proneness=injury_prone,
                important_matches=important_matches,
                ready_to_promote=False,
                season_joined=season_year,
            )
            self.session.add(candidate)
            candidates.append(candidate)

        # 5. News Item
        headline = f"{club.name} youth intake arrives"
        if is_golden:
            headline = f"GOLDEN GENERATION: Extraordinary talent arrives at {club.name}!"

        best_pot = max(c.potential_max for c in candidates) if candidates else 0
        self.session.add(NewsItem(
            season=season_year,
            matchday=matchday,
            headline=headline,
            body=(
                f"{count} new youth candidates have joined the academy. "
                f"The best prospect has potential up to {best_pot}."
            ),
            category="general",
        ))

        self.session.flush()
        return candidates

    # ── Youth development ──────────────────────────────────────────────

    def process_monthly_development(self, club_id: int):
        """Develop all youth candidates at a club for one month.

        Growth factors:
        - Personality type multiplier
        - Academy level (facility quality)
        - Random variance
        - Age (younger = more volatile growth)
        """
        club = self.session.get(Club, club_id)
        if not club:
            return

        from fm.db.models import Staff

        academy_level = club.youth_academy_level or 5
        # Facility multiplier: level 1 -> 0.7, level 5 -> 1.0, level 10 -> 1.3
        facility_mult = 0.7 + (academy_level - 1) * (0.6 / 9.0)

        # Staff influence (Youth Coach)
        youth_coach = self.session.query(Staff).filter_by(club_id=club_id, role="youth_coach").first()
        coach_mult = 1.0
        if youth_coach:
            # Average of mental and technical coaching
            coach_mult = 0.8 + ((youth_coach.coaching_mental + youth_coach.coaching_technical) / 200.0) * 0.4  # 0.8 to 1.2

        candidates = (
            self.session.query(YouthCandidate)
            .filter_by(club_id=club_id, ready_to_promote=False)
            .all()
        )

        for cand in candidates:
            personality_mult = _PERSONALITY_GROWTH_MULT.get(
                cand.personality_type or "balanced", 1.0,
            )

            # Base monthly growth: 0.5 - 2.0 CA points
            base_growth = random.uniform(0.5, 2.0)

            # Young candidates are more volatile
            age = cand.age or 16
            if age <= 15:
                base_growth *= random.uniform(0.8, 1.5)

            # Total growth
            growth = base_growth * personality_mult * facility_mult * coach_mult
            growth = max(0.0, growth * random.uniform(0.6, 1.4))

            # Apply growth (probabilistic rounding)
            int_growth = int(growth)
            frac = growth - int_growth
            actual_growth = int_growth + (1 if random.random() < frac else 0)

            # Cap at potential_max
            new_ca = min(
                cand.potential_max or 80,
                (cand.current_ability or 30) + actual_growth,
            )
            cand.current_ability = new_ca

            # Age up logic is handled in end-of-season
            # Check if ready to promote (CA >= potential_min + some threshold, or age >= 17)
            if cand.age >= 17 and new_ca >= (cand.potential_min or 50):
                cand.ready_to_promote = True
            elif cand.age >= 18:
                cand.ready_to_promote = True

        self.session.flush()

    def age_candidates(self, club_id: int):
        """Age all candidates by one year (called at end of season)."""
        candidates = (
            self.session.query(YouthCandidate)
            .filter_by(club_id=club_id)
            .all()
        )

        for cand in candidates:
            cand.age = (cand.age or 16) + 1

            # Auto-release if too old and not promoted
            if cand.age >= 20:
                self.session.delete(cand)

        self.session.flush()

    # ── Promotion to first team ────────────────────────────────────────

    def promote_to_first_team(
        self,
        candidate_id: int,
        season: int,
    ) -> Optional[Player]:
        """Promote a youth candidate to a full Player.

        Converts the YouthCandidate into a Player with generated attributes,
        deletes the candidate row, and returns the new Player.
        """
        cand = self.session.get(YouthCandidate, candidate_id)
        if not cand:
            return None

        club = self.session.get(Club, cand.club_id) if cand.club_id else None

        # Determine actual potential (random within range)
        actual_potential = random.randint(
            cand.potential_min or 50,
            cand.potential_max or 80,
        )

        # Current ability as overall
        ca = cand.current_ability or 30
        overall = max(30, min(actual_potential, ca))

        # Generate attributes based on position, archetype and overall
        attrs = self._generate_attributes(cand.position or "CM", cand.archetype, overall)

        # Generate personality attributes based on personality type
        # This fills in leadership, teamwork, etc.
        mental = self._generate_mental_from_personality(cand.personality_type or "balanced")

        # Explicitly copy the core hidden traits from candidate
        mental.update({
            "determination": cand.determination or 50,
            "professionalism": cand.professionalism or 50,
            "ambition": cand.ambition or 50,
            "loyalty": cand.loyalty or 50,
            "pressure_handling": cand.pressure or 50,
            "consistency": cand.consistency or 50,
            "injury_proneness": cand.injury_proneness or 30,
            "important_matches": cand.important_matches or 50,
        })

        # Determine wage: very low for youth
        wage = max(500, overall * 50)

        player = Player(
            name=cand.name,
            short_name=cand.name,
            age=cand.age or 17,
            nationality=cand.nationality or "England",
            position=cand.position or "CM",
            club_id=cand.club_id,
            contract_expiry=season + 3,
            wage=float(wage),
            market_value=round(max(0.05, overall * 0.01), 2),
            overall=overall,
            potential=actual_potential,
            current_ability=ca,
            potential_ability=actual_potential + random.randint(0, 15),
            squad_role="youth",
            **attrs,
            **mental,
        )

        self.session.add(player)

        # News
        club_name = club.name if club else "Unknown"
        self.session.add(NewsItem(
            season=season,
            headline=f"{cand.name} promoted from {club_name} academy",
            body=(
                f"{cand.name} ({cand.age}, {cand.position}) has been promoted "
                f"to the first team from the youth academy. "
                f"Archetype: {cand.archetype.replace('_', ' ').title() if cand.archetype else 'Generic'}."
            ),
            category="general",
        ))

        # Remove candidate
        self.session.delete(cand)
        self.session.flush()

        return player

    # ── Queries ────────────────────────────────────────────────────────

    def get_candidates(self, club_id: int) -> list[YouthCandidate]:
        """Return all youth candidates for a club."""
        return (
            self.session.query(YouthCandidate)
            .filter_by(club_id=club_id)
            .order_by(YouthCandidate.current_ability.desc())
            .all()
        )

    def get_promotable(self, club_id: int) -> list[YouthCandidate]:
        """Return candidates ready for first-team promotion."""
        return (
            self.session.query(YouthCandidate)
            .filter_by(club_id=club_id, ready_to_promote=True)
            .order_by(YouthCandidate.current_ability.desc())
            .all()
        )

    def release_candidate(self, candidate_id: int, season: int) -> bool:
        """Release a youth candidate (delete from academy)."""
        cand = self.session.get(YouthCandidate, candidate_id)
        if not cand:
            return False

        club = self.session.get(Club, cand.club_id) if cand.club_id else None
        club_name = club.name if club else "Unknown"

        self.session.add(NewsItem(
            season=season,
            headline=f"{cand.name} released from {club_name} academy",
            body=f"{cand.name} has been released from the youth academy.",
            category="general",
        ))

        self.session.delete(cand)
        self.session.flush()
        return True

    # ── Attribute generation helpers ───────────────────────────────────

    def _generate_attributes(self, position: str, archetype: str | None, overall: int) -> dict:
        """Generate position and archetype-appropriate attributes from overall rating."""
        attrs = {}

        # Position-based base weights (fallback)
        _pos_profiles: dict[str, dict[str, float]] = {
            "GK": {"gk_diving": 1.1, "gk_handling": 1.1, "gk_reflexes": 1.1, "gk_positioning": 1.1},
            "CB": {"defending": 1.1, "marking": 1.1, "standing_tackle": 1.1, "strength": 1.0, "heading_accuracy": 1.0},
            "LB": {"pace": 1.0, "acceleration": 1.0, "stamina": 1.0, "defending": 0.9, "crossing": 1.0},
            "RB": {"pace": 1.0, "acceleration": 1.0, "stamina": 1.0, "defending": 0.9, "crossing": 1.0},
            "CDM": {"defending": 1.0, "interceptions": 1.1, "standing_tackle": 1.0, "passing": 0.9, "positioning": 1.0},
            "CM": {"passing": 1.0, "short_passing": 1.0, "vision": 1.0, "stamina": 1.0, "ball_control": 0.9},
            "CAM": {"vision": 1.1, "passing": 1.0, "dribbling": 1.0, "ball_control": 1.0, "shooting": 0.9},
            "LW": {"pace": 1.1, "dribbling": 1.1, "acceleration": 1.1, "crossing": 1.0, "agility": 1.0},
            "RW": {"pace": 1.1, "dribbling": 1.1, "acceleration": 1.1, "crossing": 1.0, "agility": 1.0},
            "ST": {"finishing": 1.2, "shooting": 1.1, "positioning": 1.0, "composure": 1.0, "shot_power": 1.0},
        }

        # Start with position weights
        weights = _pos_profiles.get(position, _pos_profiles["CM"]).copy()

        # Apply archetype multipliers if available
        if archetype and archetype in ARCHETYPE_PROFILES:
            arch_weights = ARCHETYPE_PROFILES[archetype]
            for attr, mult in arch_weights.items():
                weights[attr] = mult

        # All settable attributes
        all_attrs = [
            "pace", "acceleration", "sprint_speed", "shooting", "finishing",
            "shot_power", "long_shots", "volleys", "penalties", "passing",
            "vision", "crossing", "free_kick_accuracy", "short_passing",
            "long_passing", "curve", "dribbling", "agility", "balance",
            "ball_control", "defending", "marking", "standing_tackle",
            "sliding_tackle", "interceptions", "heading_accuracy",
            "physical", "stamina", "strength", "jumping", "aggression",
            "composure", "reactions", "positioning",
        ]

        gk_attrs = [
            "gk_diving", "gk_handling", "gk_kicking",
            "gk_positioning", "gk_reflexes", "gk_speed",
        ]

        for attr in all_attrs:
            weight = weights.get(attr, 0.7)
            base = int(overall * weight)
            # Add noise
            noise = random.randint(-8, 8)
            val = max(10, min(85, base + noise))
            attrs[attr] = val

        for attr in gk_attrs:
            if position == "GK":
                weight = weights.get(attr, 1.1)
                base = int(overall * weight)
                attrs[attr] = max(10, min(88, base + random.randint(-5, 5)))
            else:
                attrs[attr] = random.randint(5, 15)

        return attrs

    def _generate_mental_from_personality(self, personality: str) -> dict:
        """Generate mental/personality attributes based on personality type."""
        # Base values with personality-specific adjustments
        base = 50
        attrs = {
            "leadership": base,
            "teamwork": base,
            "determination": base,
            "ambition": base,
            "loyalty": base,
            "temperament": base,
            "professionalism": base,
            "pressure_handling": base,
            "adaptability": base,
            "versatility": base,
            "flair": base,
        }

        _adjustments: dict[str, dict[str, int]] = {
            "determined": {"determination": 25, "ambition": 15, "professionalism": 10},
            "professional": {"professionalism": 25, "temperament": 15, "determination": 10},
            "perfectionist": {
                "professionalism": 20, "determination": 20,
                "ambition": 15, "pressure_handling": -5,
            },
            "ambitious": {"ambition": 25, "determination": 15, "loyalty": -10},
            "spirited": {"determination": 15, "teamwork": 10, "leadership": 10},
            "balanced": {},
            "casual": {
                "professionalism": -15, "determination": -10,
                "temperament": 10, "adaptability": 10,
            },
            "lazy": {
                "professionalism": -20, "determination": -20,
                "ambition": -10, "temperament": 5,
            },
            "volatile": {
                "temperament": -25, "determination": 10,
                "flair": 15, "pressure_handling": -15,
            },
        }

        adjustments = _adjustments.get(personality, {})
        for attr, adj in adjustments.items():
            if attr in attrs:
                attrs[attr] = max(10, min(90, attrs[attr] + adj + random.randint(-5, 5)))

        # Add randomness to all
        for attr in attrs:
            attrs[attr] = max(10, min(90, attrs[attr] + random.randint(-8, 8)))

        return attrs
