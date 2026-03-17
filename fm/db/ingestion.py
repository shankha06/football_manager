"""Data ingestion pipeline — download Kaggle datasets and populate the database.

Handles:
  1. EA Sports FC 24 complete player dataset → Player, Club tables
  2. Synthetic league/club seeding when datasets are incomplete
  3. Fixture generation via round-robin scheduling
  4. Financial initialisation
  5. Staff generation for each club
  6. Contract records for each player
  7. Board expectations for each club
  8. New club facility fields based on reputation/tier
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import re
from pathlib import Path
from typing import Optional

import pandas as pd

from fm.config import (
    DATA_DIR, LEAGUES_CONFIG, STARTING_SEASON,
    TIER1_BASE_BUDGET, TIER2_BASE_BUDGET,
    TV_MONEY_TIER1, TV_MONEY_TIER2,
    STAFF_WAGE_MULTIPLIER,
)
from fm.db.database import get_session, init_db
from fm.db.models import (
    League, Club, Player, Manager, TacticalSetup,
    LeagueStanding, Fixture, Season, PlayerStats,
    Staff, Contract, BoardExpectation,
)
from fm.utils.helpers import round_robin_schedule


# ── Kaggle download helpers ────────────────────────────────────────────────

def download_fc24_dataset() -> Path:
    """Return the local male_players.csv path if present."""
    csv_path = DATA_DIR / "male_players.csv"
    if csv_path.exists():
        return csv_path

    # Fallback to older name
    csv_path = DATA_DIR / "dataset.csv"
    if csv_path.exists():
        return csv_path

    # Keep original kagglehub fallback just in case
    try:
        import kagglehub
        path = kagglehub.dataset_download("stefanoleone992/ea-sports-fc-24-complete-player-dataset")
        dl_path = Path(path)
        for f in dl_path.rglob("*.csv"):
            if "male_players" in f.name.lower() or "players" in f.name.lower():
                import shutil
                shutil.copy(f, csv_path)
                return csv_path
    except Exception as e:
        print(f"[Ingestion] Could not download from Kaggle: {e}")
    return csv_path


# ── Attribute mapping ──────────────────────────────────────────────────────

# Map from EA FC 24 CSV column names to our Player model columns
ATTR_MAP = {
    "overall": "overall",
    "potential": "potential",
    "pace": "pace",
    "shooting": "shooting",
    "passing": "passing",
    "dribbling": "dribbling",
    "defending": "defending",
    "physic": "physical",
    "attacking_crossing": "crossing",
    "attacking_finishing": "finishing",
    "attacking_heading_accuracy": "heading_accuracy",
    "attacking_short_passing": "short_passing",
    "attacking_volleys": "volleys",
    "skill_dribbling": "ball_control",
    "skill_curve": "curve",
    "skill_fk_accuracy": "free_kick_accuracy",
    "skill_long_passing": "long_passing",
    "skill_ball_control": "ball_control",
    "movement_acceleration": "acceleration",
    "movement_sprint_speed": "sprint_speed",
    "movement_agility": "agility",
    "movement_reactions": "reactions",
    "movement_balance": "balance",
    "power_shot_power": "shot_power",
    "power_jumping": "jumping",
    "power_stamina": "stamina",
    "power_strength": "strength",
    "power_long_shots": "long_shots",
    "mentality_aggression": "aggression",
    "mentality_interceptions": "interceptions",
    "mentality_positioning": "positioning",
    "mentality_vision": "vision",
    "mentality_penalties": "penalties",
    "mentality_composure": "composure",
    "defending_marking_awareness": "marking",
    "defending_standing_tackle": "standing_tackle",
    "defending_sliding_tackle": "sliding_tackle",
    "goalkeeping_diving": "gk_diving",
    "goalkeeping_handling": "gk_handling",
    "goalkeeping_kicking": "gk_kicking",
    "goalkeeping_positioning": "gk_positioning",
    "goalkeeping_reflexes": "gk_reflexes",
    "goalkeeping_speed": "gk_speed",
}

# EA FC position codes → our position codes
POSITION_MAP = {
    "GK": "GK",
    "SW": "CB", "CB": "CB",
    "RB": "RB", "RWB": "RWB",
    "LB": "LB", "LWB": "LWB",
    "CDM": "CDM", "CM": "CM", "CAM": "CAM",
    "RM": "RM", "LM": "LM",
    "RW": "RW", "LW": "LW",
    "CF": "CF", "ST": "ST",
    "RF": "RW", "LF": "LW",
    "SUB": "CM", "RES": "CM",
}

# Map (FIFA league_id, league_name) to our configured league name.
# This disambiguates leagues with the same name in different countries
# (e.g. English "Premier League" id=13 vs Russian id=67).
FIFA_LEAGUE_MAP: dict[tuple[int, str], str] = {
    (13, "Premier League"):  "Premier League",
    (14, "Championship"):    "Championship",
    (60, "League One"):      "League One",
    (61, "League Two"):      "League Two",
    (53, "La Liga"):         "La Liga",
    (54, "La Liga 2"):       "La Liga 2",
    (19, "Bundesliga"):      "Bundesliga",
    (20, "2. Bundesliga"):   "2. Bundesliga",
    (2076, "3. Liga"):       "3. Liga",
    (31, "Serie A"):         "Serie A",
    (32, "Serie B"):         "Serie B",
    (16, "Ligue 1"):         "Ligue 1",
    (17, "Ligue 2"):         "Ligue 2",
    (308, "Liga Portugal"):  "Liga Portugal",
    (10, "Eredivisie"):      "Eredivisie",
    (50, "Premiership"):     "Premiership",
    (68, "Super Lig"):       "Super Lig",
    (39, "Major League Soccer"): "Major League Soccer",
}

# The FIFA version to use (latest = best data)
TARGET_FIFA_VERSION = 24.0

# ── Staff name pools ──────────────────────────────────────────────────────

_STAFF_FIRST_NAMES = [
    "Michael", "David", "Thomas", "James", "Robert", "Daniel", "Paul",
    "Antonio", "Marco", "Luis", "Carlos", "Jean", "Pierre", "Stefan",
    "Hans", "Sergio", "Giuseppe", "Patrick", "Alan", "Chris", "Rui",
    "Fabio", "Andreas", "Martin", "Henrik", "Lars", "Dieter", "Bruno",
    "Fernando", "Ricardo", "Eduardo", "Emilio", "Nikolai", "Viktor",
]
_STAFF_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Martinez", "Rodriguez", "Hernandez", "Lopez", "Gonzalez", "Rossi",
    "Ferrari", "Bianchi", "Mueller", "Schmidt", "Weber", "Fischer",
    "Dupont", "Martin", "Bernard", "Silva", "Santos", "Pereira",
    "Andersen", "Nielsen", "Johansson", "Petrov", "Novak", "Kowalski",
]


def _safe_int(val, default=50) -> int:
    """Safely convert a value to int, with a default."""
    try:
        if pd.isna(val):
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val, default=0.0) -> float:
    try:
        if pd.isna(val):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_str(val, default="") -> str:
    """Safely convert a value to string, with a default."""
    try:
        if pd.isna(val):
            return default
        s = str(val).strip()
        return s if s and s != "nan" else default
    except (ValueError, TypeError):
        return default


def _clamp(val: int | float, lo: int = 1, hi: int = 99) -> int:
    """Clamp an integer to [lo, hi]."""
    return max(lo, min(hi, int(val)))


def _extract_primary_position(pos_str: str) -> str:
    """Extract the primary position from an EA FC position string like 'ST, CF'."""
    if not pos_str or pd.isna(pos_str):
        return "CM"
    first = pos_str.split(",")[0].strip().upper()
    return POSITION_MAP.get(first, "CM")


def _extract_secondary_positions(pos_str: str) -> str:
    """Extract comma-separated secondary positions from EA FC position string."""
    if not pos_str or pd.isna(pos_str):
        return ""
    parts = [p.strip().upper() for p in pos_str.split(",")]
    mapped = []
    for p in parts[1:]:  # skip primary
        m = POSITION_MAP.get(p)
        if m and m not in mapped:
            mapped.append(m)
    return ",".join(mapped[:3])  # limit to 3 secondary positions


def _derive_personality(row, df_columns) -> dict:
    """Derive personality traits from EA FC 24 CSV attributes.

    Returns a dict of personality column → value (1-99).
    """
    ovr = _safe_int(row.get("overall", 50))
    composure = _safe_int(row.get("mentality_composure", 50))
    aggression = _safe_int(row.get("mentality_aggression", 50))
    vision = _safe_int(row.get("mentality_vision", 50))
    interceptions = _safe_int(row.get("mentality_interceptions", 50))
    positioning = _safe_int(row.get("mentality_positioning", 50))
    penalties = _safe_int(row.get("mentality_penalties", 50))
    reactions = _safe_int(row.get("movement_reactions", 50))
    stamina = _safe_int(row.get("power_stamina", 50))
    intl_rep = _safe_int(row.get("international_reputation", 1), 1)

    # Parse work rates for professionalism signal
    wr = _safe_str(row.get("work_rate", "Medium/ Medium"))
    parts = wr.replace("/", ",").split(",")
    att_wr = parts[0].strip().lower() if parts else "medium"
    def_wr = parts[1].strip().lower() if len(parts) >= 2 else "medium"
    wr_score = {"high": 80, "medium": 55, "low": 30}.get(att_wr, 55)
    def_wr_score = {"high": 80, "medium": 55, "low": 30}.get(def_wr, 55)

    # Leadership: composure + reactions + international reputation + overall
    leadership = _clamp(
        composure * 0.3 + reactions * 0.2 + intl_rep * 8 + ovr * 0.2
        + random.randint(-5, 5)
    )

    # Teamwork: vision + interceptions + def work rate + short passing
    short_pass = _safe_int(row.get("attacking_short_passing", 50))
    teamwork = _clamp(
        vision * 0.25 + interceptions * 0.2 + def_wr_score * 0.25
        + short_pass * 0.2 + random.randint(-5, 5)
    )

    # Determination: stamina + aggression + work rates
    determination = _clamp(
        stamina * 0.3 + aggression * 0.2 + wr_score * 0.2
        + def_wr_score * 0.2 + random.randint(-5, 5)
    )

    # Ambition: potential vs overall gap + international reputation
    pot = _safe_int(row.get("potential", ovr))
    gap = max(0, pot - ovr)
    ambition = _clamp(
        50 + gap * 1.5 + intl_rep * 6 + random.randint(-8, 8)
    )

    # Loyalty: inverse of ambition, modulated by age
    age = _safe_int(row.get("age", 25), 25)
    loyalty = _clamp(
        90 - ambition * 0.4 + min(age, 34) * 0.8 + random.randint(-8, 8)
    )

    # Temperament: inverse of aggression, modified by composure
    temperament = _clamp(
        composure * 0.5 + (99 - aggression) * 0.3 + random.randint(-8, 8)
    )

    # Professionalism: work rates + composure + stamina
    professionalism = _clamp(
        wr_score * 0.3 + def_wr_score * 0.2 + composure * 0.25
        + stamina * 0.15 + random.randint(-5, 5)
    )

    # Pressure handling: composure + penalties + reactions
    pressure_handling = _clamp(
        composure * 0.4 + penalties * 0.25 + reactions * 0.2
        + random.randint(-5, 5)
    )

    # Adaptability: agility + balance + vision (mental flexibility)
    agility = _safe_int(row.get("movement_agility", 50))
    balance = _safe_int(row.get("movement_balance", 50))
    adaptability = _clamp(
        agility * 0.25 + balance * 0.2 + vision * 0.3
        + random.randint(-8, 8)
    )

    # Versatility: count of positions the player can play
    pos_str = _safe_str(row.get("player_positions", ""))
    num_pos = len([p for p in pos_str.split(",") if p.strip()])
    versatility = _clamp(
        40 + num_pos * 8 + agility * 0.15 + random.randint(-5, 5)
    )

    # Dirtiness: aggression + inverse of composure
    dirtiness = _clamp(
        aggression * 0.5 + (99 - composure) * 0.3 + random.randint(-8, 8)
    )

    # Flair: skill_moves + dribbling + curve
    skill_moves = _safe_int(row.get("skill_moves", 2), 2)
    skill_dribbling = _safe_int(row.get("skill_dribbling", 50))
    curve = _safe_int(row.get("skill_curve", 50))
    flair = _clamp(
        skill_moves * 12 + skill_dribbling * 0.2 + curve * 0.2
        + random.randint(-5, 5)
    )

    # Important matches: composure + overall + international rep
    important_matches = _clamp(
        composure * 0.35 + ovr * 0.25 + intl_rep * 8
        + random.randint(-5, 5)
    )

    return {
        "leadership": leadership,
        "teamwork": teamwork,
        "determination": determination,
        "ambition": ambition,
        "loyalty": loyalty,
        "temperament": temperament,
        "professionalism": professionalism,
        "pressure_handling": pressure_handling,
        "adaptability": adaptability,
        "versatility": versatility,
        "dirtiness": dirtiness,
        "flair": flair,
        "important_matches": important_matches,
    }


def _derive_hidden_attributes(row) -> dict:
    """Derive hidden attributes from correlated CSV data.

    Returns a dict of hidden attribute column → value.
    """
    ovr = _safe_int(row.get("overall", 50))
    pot = _safe_int(row.get("potential", ovr))
    composure = _safe_int(row.get("mentality_composure", 50))
    reactions = _safe_int(row.get("movement_reactions", 50))
    age = _safe_int(row.get("age", 25), 25)

    # Consistency: higher overall players are more consistent; age helps
    consistency = _clamp(
        ovr * 0.5 + reactions * 0.2 + min(age, 32) * 0.8
        + random.randint(-8, 8),
        lo=30, hi=95,
    )

    # Injury proneness: somewhat random but light players and older = more prone
    weight = _safe_int(row.get("weight_kg", 75), 75)
    stamina = _safe_int(row.get("power_stamina", 50))
    injury_proneness = _clamp(
        50 - stamina * 0.2 - min(weight, 90) * 0.15
        + max(0, age - 30) * 3
        + random.randint(-10, 15),
        lo=10, hi=85,
    )

    # Big match: composure-driven
    big_match = _clamp(
        composure * 0.45 + ovr * 0.2 + random.randint(-10, 10),
        lo=30, hi=95,
    )

    return {
        "consistency": consistency,
        "injury_proneness": injury_proneness,
        "big_match": big_match,
    }


def _derive_ability_ratings(row) -> dict:
    """Map overall/potential (1-99) to current_ability/potential_ability (1-200)."""
    ovr = _safe_int(row.get("overall", 50))
    pot = _safe_int(row.get("potential", ovr))
    # Linear mapping: 40 overall -> ~60 CA, 99 overall -> ~200 CA
    # Formula: CA = (overall - 25) * (200 / 74) clamped to [1, 200]
    ca = _clamp(int((ovr - 25) * 2.7), lo=1, hi=200)
    pa = _clamp(int((pot - 25) * 2.7), lo=ca, hi=200)
    return {"current_ability": ca, "potential_ability": pa}


def _derive_squad_role(ovr: int, age: int, club_reputation: int) -> str:
    """Derive a reasonable squad role from overall, age, and club reputation."""
    # Compare player overall to what the club would expect
    if club_reputation >= 80:
        thresholds = (85, 78, 72, 65)
    elif club_reputation >= 60:
        thresholds = (80, 73, 67, 60)
    elif club_reputation >= 40:
        thresholds = (75, 68, 62, 55)
    else:
        thresholds = (70, 63, 57, 50)

    if ovr >= thresholds[0]:
        return "star_player"
    elif ovr >= thresholds[1]:
        return "first_team"
    elif ovr >= thresholds[2]:
        return "rotation"
    elif ovr >= thresholds[3]:
        if age <= 21:
            return "youth"
        return "backup"
    else:
        if age <= 21:
            return "youth"
        return "backup"


def _derive_match_readiness(ovr: int, age: int) -> dict:
    """Derive initial match readiness values."""
    # Start-of-season values: established players have higher baselines
    base_sharpness = 55.0 + ovr * 0.2 + random.uniform(-5, 5)
    # Younger players adapt faster but start lower on tactical familiarity
    tac_fam = 40.0 + min(age - 17, 15) * 2.0 + random.uniform(-5, 5)
    chemistry = 45.0 + min(age - 17, 10) * 1.5 + random.uniform(-5, 5)
    return {
        "match_sharpness": max(30.0, min(90.0, base_sharpness)),
        "tactical_familiarity": max(20.0, min(80.0, tac_fam)),
        "team_chemistry": max(20.0, min(80.0, chemistry)),
    }


def _parse_release_clause(row) -> float | None:
    """Parse release_clause_eur from CSV, return in millions or None."""
    val = row.get("release_clause_eur", None)
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
        f = float(val)
        if f <= 0:
            return None
        return f / 1_000_000.0
    except (ValueError, TypeError):
        return None


def _parse_traits(row) -> str | None:
    """Parse player_traits from CSV into a JSON list string."""
    raw = _safe_str(row.get("player_traits", ""))
    if not raw:
        return None
    # EA FC 24 stores traits as comma-separated string
    traits = [t.strip() for t in raw.split(",") if t.strip()]
    if not traits:
        return None
    return json.dumps(traits)


# ── Main ingestion ─────────────────────────────────────────────────────────

def ingest_all(db_path=None, download: bool = True) -> dict:
    """Run the full ingestion pipeline.

    Returns a summary dict with counts.
    """
    init_db(db_path)
    session = get_session()
    stats = {"leagues": 0, "clubs": 0, "players": 0, "fixtures": 0,
             "staff": 0, "contracts": 0, "board_expectations": 0}

    try:
        # 1. Seed leagues
        leagues = _seed_leagues(session)
        stats["leagues"] = len(leagues)

        # 2. Try to load player data from Kaggle CSV
        csv_path = None
        if download:
            csv_path = download_fc24_dataset()

        if csv_path and csv_path.exists():
            clubs, players = _ingest_from_csv(session, csv_path, leagues)
            stats["clubs"] = clubs
            stats["players"] = players
        else:
            # Synthetic data fallback
            clubs, players = _generate_synthetic_data(session, leagues)
            stats["clubs"] = clubs
            stats["players"] = players

        # 3. Ensure all clubs have managers and tactical setups
        _ensure_managers(session)
        _ensure_tactical_setups(session)

        # 4. Generate staff for each club
        stats["staff"] = _generate_staff(session)

        # 5. Create contract records for all players
        stats["contracts"] = _generate_contracts(session)

        # 6. Create board expectations for each club
        stats["board_expectations"] = _generate_board_expectations(session)

        # 7. Populate new club facility fields
        _populate_club_facilities(session)

        # 8. Generate fixtures
        fixtures = _generate_all_fixtures(session, leagues)
        stats["fixtures"] = fixtures

        # 9. Initialise standings
        _init_standings(session, leagues)

        # 10. Create season record
        _init_season(session)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return stats


def _seed_leagues(session) -> list[League]:
    """Create league records from config."""
    leagues = []
    for lc in LEAGUES_CONFIG:
        existing = session.query(League).filter_by(name=lc["name"]).first()
        if existing:
            leagues.append(existing)
            continue
        league = League(
            name=lc["name"],
            country=lc["country"],
            tier=lc["tier"],
            num_teams=lc["num_teams"],
            promotion_spots=lc["promo"],
            relegation_spots=lc["releg"],
        )
        session.add(league)
        session.flush()
        leagues.append(league)
    return leagues


def _ingest_from_csv(session, csv_path: Path, leagues: list[League]):
    """Parse the EA FC 24 CSV and populate Club + Player tables.

    Only imports the latest FIFA version and uses (league_id, league_name)
    to correctly disambiguate leagues with the same name across countries.
    Now also populates: personality traits, hidden attributes, physical profile,
    current_ability/potential_ability, contract details, traits, squad roles,
    and match readiness.
    """
    df = pd.read_csv(csv_path, low_memory=False)

    # Normalise column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # ── Filter to latest FIFA version only ────────────────────────────────
    if "fifa_version" in df.columns:
        available_versions = df["fifa_version"].dropna().unique()
        target = TARGET_FIFA_VERSION
        if target not in available_versions:
            target = max(available_versions)
        df = df[df["fifa_version"] == target].copy()
        print(f"[Ingestion] Using FIFA version {target} ({len(df)} player rows)")

    # Build a league-name → League object lookup
    league_by_name = {lg.name: lg for lg in leagues}

    # Track clubs we create
    club_cache: dict[str, Club] = {}
    club_count = 0
    player_count = 0

    # Figure out which columns exist
    club_col = None
    for candidate in ["club_name", "club", "club_team_id"]:
        if candidate in df.columns:
            club_col = candidate
            break

    league_name_col = None
    for candidate in ["league_name", "league"]:
        if candidate in df.columns:
            league_name_col = candidate
            break

    # FIFA's internal league_id (identifies country, NOT the same as our DB id)
    fifa_league_id_col = None
    if "league_id" in df.columns:
        fifa_league_id_col = "league_id"

    pos_col = None
    for candidate in ["player_positions", "club_position", "position"]:
        if candidate in df.columns:
            pos_col = candidate
            break

    name_col = None
    for candidate in ["long_name", "player_name", "name"]:
        if candidate in df.columns:
            name_col = candidate
            break

    short_name_col = None
    for candidate in ["short_name", "known_as"]:
        if candidate in df.columns:
            short_name_col = candidate
            break

    seen_players: set[int] = set()  # deduplicate by player_id

    for _, row in df.iterrows():
        # Deduplicate players (same player can appear with different updates)
        pid = _safe_int(row.get("player_id", 0), 0)
        if pid in seen_players:
            continue
        if pid:
            seen_players.add(pid)

        # Get or create club
        club_name = str(row.get(club_col, "Unknown")) if club_col else "Unknown"
        if club_name in ("nan", "None", ""):
            continue

        if club_name not in club_cache:
            # Match league using (fifa_league_id, league_name) for accuracy
            lg_name = str(row.get(league_name_col, "")).strip() if league_name_col else ""
            fifa_lid = _safe_int(row.get(fifa_league_id_col, 0), 0) if fifa_league_id_col else 0

            matched_league = None
            config_name = FIFA_LEAGUE_MAP.get((fifa_lid, lg_name))
            if config_name and config_name in league_by_name:
                matched_league = league_by_name[config_name]

            # Skip clubs not in our configured leagues
            if not matched_league:
                continue

            club = Club(
                name=club_name,
                short_name=club_name[:30],
                league_id=matched_league.id,
                reputation=_safe_int(row.get("international_reputation",
                                             row.get("club_overall", 50)), 50),
            )
            session.add(club)
            session.flush()
            club_cache[club_name] = club
            club_count += 1

        club = club_cache[club_name]

        # Create player
        pname = str(row.get(name_col, "Unknown Player")) if name_col else "Unknown"
        sname = str(row.get(short_name_col, "")) if short_name_col else ""
        pos_raw = str(row.get(pos_col, "CM")) if pos_col else "CM"
        position = _extract_primary_position(pos_raw)

        ovr = _safe_int(row.get("overall", 50))
        pot = _safe_int(row.get("potential", ovr))
        age = _safe_int(row.get("age", 25), 25)
        contract_expiry = _safe_int(
            row.get("club_contract_valid_until_year", 2026), 2026)

        player = Player(
            name=pname,
            short_name=sname or pname.split()[-1] if pname else "Player",
            age=age,
            nationality=str(row.get("nationality_name",
                                    row.get("nationality", "Unknown"))),
            position=position,
            secondary_positions=_extract_secondary_positions(pos_raw),
            club_id=club.id,
            overall=ovr,
            potential=pot,
            wage=_safe_float(row.get("wage_eur", 0)) / 1000.0,  # in K
            market_value=_safe_float(row.get("value_eur", 0)) / 1_000_000.0,
            contract_expiry=contract_expiry,
        )

        # Map detailed attributes
        for csv_col, model_col in ATTR_MAP.items():
            if csv_col in df.columns:
                setattr(player, model_col, _safe_int(row.get(csv_col, 50)))

        # Work rates
        for wr_col in ["work_rate", "attacking_work_rate"]:
            if wr_col in df.columns:
                wr = str(row.get(wr_col, "Medium/ Medium"))
                parts = wr.replace("/", ",").split(",")
                if len(parts) >= 2:
                    player.att_work_rate = parts[0].strip().lower()
                    player.def_work_rate = parts[1].strip().lower()

        # ── Physical profile ──────────────────────────────────────────────
        player.height_cm = _safe_int(row.get("height_cm", 180), 180)
        player.weight_kg = _safe_int(row.get("weight_kg", 75), 75)

        pfoot = _safe_str(row.get("preferred_foot", "Right")).lower()
        player.preferred_foot = pfoot if pfoot in ("right", "left") else "right"

        player.weak_foot_ability = _clamp(
            _safe_int(row.get("weak_foot", 3), 3), lo=1, hi=5)

        # ── Traits ────────────────────────────────────────────────────────
        player.traits = _parse_traits(row)

        # ── Personality traits (derived from CSV attributes) ──────────────
        personality = _derive_personality(row, df.columns)
        for attr, val in personality.items():
            setattr(player, attr, val)

        # ── Hidden attributes ─────────────────────────────────────────────
        hidden = _derive_hidden_attributes(row)
        for attr, val in hidden.items():
            setattr(player, attr, val)

        # ── Ability ratings (1-200 scale) ─────────────────────────────────
        ability = _derive_ability_ratings(row)
        player.current_ability = ability["current_ability"]
        player.potential_ability = ability["potential_ability"]

        # ── Contract details on Player model ──────────────────────────────
        player.release_clause = _parse_release_clause(row)

        # ── Squad role ────────────────────────────────────────────────────
        player.squad_role = _derive_squad_role(ovr, age, club.reputation)

        # ── Match readiness (pre-season values) ──────────────────────────
        readiness = _derive_match_readiness(ovr, age)
        player.match_sharpness = readiness["match_sharpness"]
        player.tactical_familiarity = readiness["tactical_familiarity"]
        player.team_chemistry = readiness["team_chemistry"]

        # ── Happiness / mental state ──────────────────────────────────────
        player.happiness = max(40.0, min(85.0,
            60.0 + (ovr - 65) * 0.3 + random.uniform(-5, 5)))
        player.loyalty_to_manager = max(30.0, min(80.0,
            50.0 + random.uniform(-10, 10)))
        player.morale = max(45.0, min(80.0,
            65.0 + random.uniform(-8, 8)))
        player.form = max(45.0, min(80.0,
            65.0 + random.uniform(-8, 8)))

        session.add(player)
        player_count += 1

        # Batch flush
        if player_count % 500 == 0:
            session.flush()

    session.flush()

    # ── Cross-reference with male_teams.csv for financial data ──────────
    teams_csv = DATA_DIR / "male_teams.csv"
    teams_data: dict[str, dict] = {}
    if teams_csv.exists():
        try:
            df_teams = pd.read_csv(teams_csv, low_memory=False)
            df_teams.columns = [c.strip().lower().replace(" ", "_") for c in df_teams.columns]
            # Filter to FIFA version 24
            if "fifa_version" in df_teams.columns:
                tv = TARGET_FIFA_VERSION
                available = df_teams["fifa_version"].dropna().unique()
                if tv not in available:
                    tv = max(available)
                df_teams = df_teams[df_teams["fifa_version"] == tv].copy()
            for _, row in df_teams.iterrows():
                tname = str(row.get("team_name", "")).strip()
                if not tname or tname == "nan":
                    continue
                transfer_budget = _safe_float(row.get("transfer_budget_eur", 0))
                club_worth = _safe_float(row.get("club_worth_eur", 0))
                intl_prestige = _safe_float(row.get("international_prestige", 5))
                dom_prestige = _safe_float(row.get("domestic_prestige", 5))
                new_data = {
                    "transfer_budget": transfer_budget / 1_000_000.0,
                    "club_worth": club_worth / 1_000_000.0,
                    "international_prestige": intl_prestige,
                    "domestic_prestige": dom_prestige,
                    "home_stadium": str(row.get("home_stadium", "")),
                }
                # Keep the row with highest prestige if duplicate team names
                existing = teams_data.get(tname)
                if existing:
                    old_total = existing["international_prestige"] + existing["domestic_prestige"]
                    new_total = intl_prestige + dom_prestige
                    if new_total <= old_total:
                        continue
                teams_data[tname] = new_data
            print(f"[Ingestion] Loaded {len(teams_data)} teams from male_teams.csv")
        except Exception as e:
            print(f"[Ingestion] Could not load teams CSV: {e}")

    # Assign financial data to clubs — prefer CSV data, fall back to defaults
    for club in club_cache.values():
        td = teams_data.get(club.name)
        if td:
            # Reputation from prestige first (used in budget fallback)
            intl = td["international_prestige"]
            dom = td["domestic_prestige"]
            club.reputation = max(1, min(100, int((intl + dom) * 5)))

            # Budget: prefer transfer_budget_eur, fall back to club_worth-based estimate
            if td["transfer_budget"] > 0:
                club.budget = td["transfer_budget"]
            elif td["club_worth"] > 0:
                # Estimate transfer budget as ~2-5% of club worth
                club.budget = td["club_worth"] * 0.03
            else:
                league = session.query(League).get(club.league_id) if club.league_id else None
                tier = league.tier if league else 2
                base = TIER1_BASE_BUDGET if tier == 1 else TIER2_BASE_BUDGET
                club.budget = base * (club.reputation / 50.0)

            # Stadium capacity and name from teams CSV
            combined = intl + dom
            if combined >= 16:
                base_capacity = 75000
            elif combined >= 12:
                base_capacity = 55000
            elif combined >= 8:
                base_capacity = 35000
            elif combined >= 5:
                base_capacity = 20000
            else:
                base_capacity = 10000

            # Rectification: boost capacity for high-reputation clubs
            rep_factor = club.reputation / 100.0
            min_capacity = int(10000 + rep_factor * 50000)
            club.stadium_capacity = max(base_capacity, min_capacity)

            stadium_name = td.get("home_stadium", "")
            if stadium_name and stadium_name != "nan":
                club.stadium_name = stadium_name

            # Ensure budget isn't too low for the club's size
            league = session.query(League).get(club.league_id) if club.league_id else None
            tier = league.tier if league else 2
            min_budget = (5.0 if tier == 1 else 1.0) * (club.reputation / 50.0)
            club.budget = max(club.budget or 0.0, min_budget)

            club.wage_budget = club.budget * 0.6
        elif club.league_id:
            # Fallback: assign defaults based on tier
            league = session.query(League).get(club.league_id)
            tier = league.tier if league else 2
            if tier == 1:
                club.budget = TIER1_BASE_BUDGET * (club.reputation / 50.0)
                club.wage_budget = club.budget * 0.6
            else:
                club.budget = TIER2_BASE_BUDGET * (club.reputation / 50.0)
                club.wage_budget = club.budget * 0.5

    session.flush()
    print(f"[Ingestion] Created {club_count} clubs, {player_count} players")
    return club_count, player_count


def _generate_synthetic_data(session, leagues: list[League]):
    """Generate synthetic clubs and players when no CSV is available."""
    club_count = 0
    player_count = 0
    first_names = [
        "James", "John", "Carlos", "Marco", "Lucas", "Pierre", "Mohamed",
        "Alex", "David", "Thomas", "Hugo", "Liam", "Noah", "Mateo", "Leo",
        "Rafael", "Kai", "Yuki", "Omar", "Ivan",
    ]
    last_names = [
        "Silva", "Martinez", "Mueller", "Rossi", "Dupont", "Smith", "Jones",
        "Garcia", "Anderson", "Taylor", "Williams", "Brown", "Johnson",
        "Santos", "Kim", "Chen", "Ali", "Nakamura", "Petrov", "Andersen",
    ]
    club_suffixes = [
        "FC", "United", "City", "Athletic", "Sporting", "Real", "Inter",
        "Dynamo", "Olympique", "Borussia",
    ]
    city_names = [
        "Westfield", "Northampton", "Eastbourne", "Southport", "Riverdale",
        "Lakewood", "Hillside", "Brookfield", "Springfield", "Greenville",
        "Oakdale", "Fairview", "Milltown", "Clearwater", "Stonegate",
        "Harborview", "Kingsbridge", "Ashford", "Chelton", "Bramley",
        "Castleford", "Dunmore", "Elmswood", "Foxdale", "Glenmore",
    ]

    for league in leagues:
        for i in range(league.num_teams):
            city = random.choice(city_names) + str(random.randint(1, 99))
            suffix = random.choice(club_suffixes)
            club = Club(
                name=f"{city} {suffix}",
                short_name=f"{city[:3].upper()}{suffix[:2].upper()}",
                league_id=league.id,
                reputation=random.randint(30, 90),
                budget=(TIER1_BASE_BUDGET if league.tier == 1
                        else TIER2_BASE_BUDGET) * random.uniform(0.5, 2.0),
            )
            club.wage_budget = club.budget * 0.55
            session.add(club)
            session.flush()
            club_count += 1

            # Generate 25 players per club
            positions_needed = (
                ["GK", "GK"] +
                ["CB"] * 4 + ["LB", "RB"] +
                ["CDM"] * 2 + ["CM"] * 3 + ["CAM"] +
                ["LW", "RW"] +
                ["ST"] * 2 + ["CF"] +
                random.choices(["CM", "CB", "ST", "LW", "RW", "CDM", "CAM"], k=5)
            )

            for pos in positions_needed:
                base_ovr = random.randint(
                    45 if league.tier == 2 else 55,
                    75 if league.tier == 2 else 92,
                )
                first = random.choice(first_names)
                last = random.choice(last_names)
                p_age = random.randint(17, 36)
                p_pot = base_ovr + random.randint(0, 15)
                player = Player(
                    name=f"{first} {last}",
                    short_name=last,
                    age=p_age,
                    nationality="Synthetic",
                    position=pos,
                    club_id=club.id,
                    overall=base_ovr,
                    potential=p_pot,
                    wage=base_ovr * random.uniform(0.5, 3.0),
                    market_value=base_ovr * random.uniform(0.1, 1.5),
                )

                # Randomise attributes around overall
                for attr in [
                    "pace", "shooting", "passing", "dribbling", "defending",
                    "physical", "finishing", "heading_accuracy", "short_passing",
                    "volleys", "curve", "free_kick_accuracy", "long_passing",
                    "acceleration", "sprint_speed", "agility", "reactions",
                    "balance", "shot_power", "jumping", "stamina", "strength",
                    "long_shots", "aggression", "interceptions", "positioning",
                    "vision", "penalties", "composure", "marking",
                    "standing_tackle", "sliding_tackle", "ball_control",
                ]:
                    val = base_ovr + random.randint(-15, 15)
                    setattr(player, attr, max(1, min(99, val)))

                if pos == "GK":
                    for gk_attr in ["gk_diving", "gk_handling", "gk_kicking",
                                    "gk_positioning", "gk_reflexes"]:
                        setattr(player, gk_attr,
                                max(1, min(99, base_ovr + random.randint(-10, 10))))

                player.consistency = random.randint(50, 85)
                player.injury_proneness = random.randint(15, 60)
                player.big_match = random.randint(40, 85)

                # New fields for synthetic players
                player.height_cm = random.randint(165, 200)
                player.weight_kg = random.randint(60, 95)
                player.preferred_foot = random.choice(["right", "right", "right", "left"])
                player.weak_foot_ability = random.randint(1, 4)
                player.current_ability = _clamp(int((base_ovr - 25) * 2.7), lo=1, hi=200)
                player.potential_ability = _clamp(int((p_pot - 25) * 2.7),
                                                  lo=player.current_ability, hi=200)
                player.squad_role = _derive_squad_role(base_ovr, p_age, club.reputation)
                player.contract_expiry = STARTING_SEASON + random.randint(1, 4)

                # Personality
                for pattr in ["leadership", "teamwork", "determination", "ambition",
                              "loyalty", "temperament", "professionalism",
                              "pressure_handling", "adaptability", "versatility",
                              "dirtiness", "flair", "important_matches"]:
                    setattr(player, pattr, random.randint(35, 80))

                readiness = _derive_match_readiness(base_ovr, p_age)
                player.match_sharpness = readiness["match_sharpness"]
                player.tactical_familiarity = readiness["tactical_familiarity"]
                player.team_chemistry = readiness["team_chemistry"]
                player.happiness = 60.0 + random.uniform(-5, 10)
                player.morale = 65.0 + random.uniform(-8, 8)
                player.form = 65.0 + random.uniform(-8, 8)

                session.add(player)
                player_count += 1

        session.flush()

    return club_count, player_count


def _ensure_managers(session):
    """Ensure every club has a manager, using real data if available."""
    clubs = session.query(Club).all()

    real_coaches = {}
    team_to_coach = {}

    # Try loading real coaches
    coaches_path = DATA_DIR / "male_coaches.csv"
    teams_path = DATA_DIR / "male_teams.csv"

    if coaches_path.exists() and teams_path.exists():
        try:
            df_c = pd.read_csv(coaches_path, usecols=['coach_id', 'short_name', 'long_name'])
            for _, row in df_c.iterrows():
                real_coaches[str(row['coach_id'])] = str(row['long_name']) if pd.notna(row['long_name']) else str(row['short_name'])

            df_t = pd.read_csv(teams_path, usecols=['team_name', 'coach_id', 'def_style', 'off_style'])
            for _, row in df_t.iterrows():
                cid = str(row['coach_id'])
                if cid in real_coaches:
                    team_to_coach[str(row['team_name'])] = {
                         'name': real_coaches[cid],
                         'style': str(row.get('off_style', 'balanced')).lower()
                    }
        except Exception as e:
            print(f"Error loading coach data: {e}")

    ai_first_names = ["Pep", "Carlo", "Jurgen", "Diego", "Jose",
                      "Zinedine", "Arsene", "Alex", "Roberto", "Claudio"]
    ai_last_names = ["Garcia", "Rossi", "Schmidt", "Santos", "Martin",
                     "Anderson", "Petrov", "Yamamoto", "Chen", "Ali"]
    styles = ["attacking", "defensive", "balanced", "pragmatic",
              "possession", "counter_attack"]
    formations = ["4-4-2", "4-3-3", "4-2-3-1", "3-5-2", "4-1-4-1"]

    for club in clubs:
        if not session.query(Manager).filter_by(club_id=club.id).first():
            real_info = team_to_coach.get(club.name)
            if real_info:
                m_name = real_info['name']
                style = "attacking" if "offensive" in real_info['style'] else "balanced"
            else:
                m_name = f"{random.choice(ai_first_names)} {random.choice(ai_last_names)}"
                style = random.choice(styles)

            mgr = Manager(
                name=m_name,
                club_id=club.id,
                is_human=False,
                tactical_style=style,
                reputation=max(20, club.reputation + random.randint(-20, 10)),
                preferred_formation=random.choice(formations),
            )
            session.add(mgr)
    session.flush()


def _ensure_tactical_setups(session):
    """Ensure every club has a tactical setup."""
    clubs = session.query(Club).all()
    for club in clubs:
        if not session.query(TacticalSetup).filter_by(club_id=club.id).first():
            mgr = session.query(Manager).filter_by(club_id=club.id).first()
            ts = TacticalSetup(
                club_id=club.id,
                formation=mgr.preferred_formation if mgr else "4-4-2",
                mentality="balanced",
                tempo="normal",
                pressing="standard",
                passing_style="mixed",
                width="normal",
            )
            session.add(ts)
    session.flush()


# ── Staff generation ──────────────────────────────────────────────────────

# Roles to generate for each club and their count
_STAFF_ROLES = [
    ("assistant", 1),
    ("gk_coach", 1),
    ("fitness_coach", 1),
    ("scout", 2),
    ("chief_scout", 1),
    ("physio", 1),
    ("analyst", 1),
    ("youth_coach", 1),
    ("set_piece_coach", 1),
]


def _generate_staff(session) -> int:
    """Generate coaching/support staff for every club that lacks them."""
    clubs = session.query(Club).all()
    count = 0

    for club in clubs:
        existing_roles = {
            s.role for s in session.query(Staff).filter_by(club_id=club.id).all()
        }

        rep = club.reputation or 50
        league = session.query(League).get(club.league_id) if club.league_id else None
        tier = league.tier if league else 2

        # Base attribute quality scales with club reputation
        # rep 90 -> base ~70, rep 50 -> base ~45, rep 20 -> base ~30
        base_quality = max(25, min(80, int(rep * 0.65 + tier * (-3) + 10)))

        for role, num in _STAFF_ROLES:
            for i in range(num):
                # If multiple of the same role, tag them (scout_1, scout_2 etc.)
                role_key = role if num == 1 else f"{role}_{i}"
                if role in existing_roles:
                    # Only skip if we already have at least one of this role
                    existing_count = sum(
                        1 for s in session.query(Staff).filter_by(
                            club_id=club.id, role=role).all()
                    )
                    if existing_count >= num:
                        continue

                staff = _create_staff_member(club, role, base_quality, tier)
                session.add(staff)
                count += 1

        # Batch flush per club
        if count % 50 == 0:
            session.flush()

    session.flush()
    print(f"[Ingestion] Created {count} staff members")
    return count


def _create_staff_member(club: Club, role: str, base_quality: int, tier: int) -> Staff:
    """Create a single staff member with attributes appropriate to club quality."""
    name = f"{random.choice(_STAFF_FIRST_NAMES)} {random.choice(_STAFF_LAST_NAMES)}"
    age = random.randint(30, 65)
    rep = max(10, min(90, base_quality + random.randint(-15, 10)))

    # Wage from config multipliers, scaled by club reputation
    wage_mult = STAFF_WAGE_MULTIPLIER.get(role, 0.3)
    base_wage = (club.reputation or 50) * 0.15  # rough K/week
    wage = max(0.5, base_wage * wage_mult + random.uniform(-0.5, 0.5))

    # Contract expires 1-4 years from now
    contract_expiry = STARTING_SEASON + random.randint(1, 4)

    # Generate attributes with role-appropriate specialisation
    q = base_quality  # shorthand

    # General coaching attributes
    coaching_attacking = _clamp(q + random.randint(-10, 10))
    coaching_defending = _clamp(q + random.randint(-10, 10))
    coaching_tactical = _clamp(q + random.randint(-10, 10))
    coaching_technical = _clamp(q + random.randint(-10, 10))
    coaching_mental = _clamp(q + random.randint(-10, 10))
    coaching_fitness = _clamp(q + random.randint(-10, 10))
    coaching_gk = _clamp(q + random.randint(-15, 5))  # lower default for non-GK coaches

    # Role-specific boosts
    scouting_ability = _clamp(q * 0.6 + random.randint(-5, 5))
    scouting_potential_judge = _clamp(q * 0.6 + random.randint(-5, 5))
    physiotherapy = _clamp(q * 0.6 + random.randint(-5, 5))
    sports_science = _clamp(q * 0.6 + random.randint(-5, 5))
    motivation = _clamp(q + random.randint(-10, 10))
    discipline = _clamp(q + random.randint(-10, 10))
    man_management = _clamp(q + random.randint(-10, 10))

    if role == "assistant":
        # Jack of all trades, slightly lower than head coach
        coaching_tactical = _clamp(q + random.randint(-5, 12))
        man_management = _clamp(q + random.randint(-5, 10))
    elif role == "gk_coach":
        coaching_gk = _clamp(q + random.randint(5, 20))
        # Other coaching attrs lower
        coaching_attacking = _clamp(q * 0.5 + random.randint(-5, 5))
    elif role == "fitness_coach":
        coaching_fitness = _clamp(q + random.randint(5, 20))
        sports_science = _clamp(q + random.randint(0, 15))
        coaching_attacking = _clamp(q * 0.5 + random.randint(-5, 5))
    elif role in ("scout", "chief_scout"):
        scouting_ability = _clamp(q + random.randint(-5, 15))
        scouting_potential_judge = _clamp(q + random.randint(-5, 15))
        if role == "chief_scout":
            scouting_ability = _clamp(q + random.randint(0, 20))
            scouting_potential_judge = _clamp(q + random.randint(0, 20))
        # Scouts have lower coaching
        coaching_attacking = _clamp(q * 0.4 + random.randint(-5, 5))
        coaching_defending = _clamp(q * 0.4 + random.randint(-5, 5))
    elif role == "physio":
        physiotherapy = _clamp(q + random.randint(5, 20))
        sports_science = _clamp(q + random.randint(0, 15))
        coaching_attacking = _clamp(q * 0.3 + random.randint(-5, 5))
    elif role == "analyst":
        coaching_tactical = _clamp(q + random.randint(0, 15))
        coaching_mental = _clamp(q + random.randint(0, 10))
    elif role == "youth_coach":
        coaching_mental = _clamp(q + random.randint(0, 15))
        coaching_technical = _clamp(q + random.randint(0, 12))
        man_management = _clamp(q + random.randint(0, 12))
    elif role == "set_piece_coach":
        coaching_tactical = _clamp(q + random.randint(0, 15))
        coaching_technical = _clamp(q + random.randint(0, 12))

    nationality_pool = [
        "English", "Spanish", "German", "Italian", "French", "Portuguese",
        "Dutch", "Brazilian", "Argentine", "Scottish", "Welsh", "Irish",
    ]

    return Staff(
        name=name,
        club_id=club.id,
        role=role,
        nationality=random.choice(nationality_pool),
        age=age,
        coaching_attacking=coaching_attacking,
        coaching_defending=coaching_defending,
        coaching_tactical=coaching_tactical,
        coaching_technical=coaching_technical,
        coaching_mental=coaching_mental,
        coaching_fitness=coaching_fitness,
        coaching_gk=coaching_gk,
        scouting_ability=scouting_ability,
        scouting_potential_judge=scouting_potential_judge,
        physiotherapy=physiotherapy,
        sports_science=sports_science,
        motivation=motivation,
        discipline=discipline,
        man_management=man_management,
        wage=wage,
        contract_expiry=contract_expiry,
        reputation=rep,
    )


# ── Contract generation ───────────────────────────────────────────────────

def _generate_contracts(session) -> int:
    """Create Contract model instances for every player that lacks one."""
    players = session.query(Player).filter(Player.club_id.isnot(None)).all()
    count = 0

    for player in players:
        # Skip if player already has an active contract
        existing = session.query(Contract).filter_by(
            player_id=player.id, is_active=True
        ).first()
        if existing:
            continue

        club = session.query(Club).get(player.club_id)
        if not club:
            continue

        ovr = player.overall or 50
        age = player.age or 25
        wage = player.wage or 0.0

        # Contract end year: use player's contract_expiry field
        end_year = player.contract_expiry or (STARTING_SEASON + random.randint(1, 4))
        # Start year: estimate based on end year and typical contract length
        contract_length = max(1, end_year - STARTING_SEASON)
        start_year = end_year - min(contract_length, random.randint(2, 5))
        if start_year > STARTING_SEASON:
            start_year = STARTING_SEASON - random.randint(0, 2)

        # Signing bonus: higher for better players
        signing_bonus = None
        if ovr >= 75 and random.random() < 0.6:
            signing_bonus = wage * random.uniform(4, 12)
        elif ovr >= 65 and random.random() < 0.3:
            signing_bonus = wage * random.uniform(2, 6)

        # Loyalty bonus: occasional
        loyalty_bonus = None
        if random.random() < 0.2:
            loyalty_bonus = wage * random.uniform(2, 8)

        # Release clause: use player's if set, else derive
        release_clause = player.release_clause
        if release_clause is None and ovr >= 70 and random.random() < 0.5:
            release_clause = player.market_value * random.uniform(1.5, 4.0) if player.market_value else None

        # Foreign release clause: occasionally higher
        release_clause_foreign = None
        if release_clause and random.random() < 0.3:
            release_clause_foreign = release_clause * random.uniform(1.2, 2.0)

        # Performance bonuses
        appearance_bonus = 0.0
        goal_bonus = 0.0
        assist_bonus = 0.0
        clean_sheet_bonus = 0.0

        if ovr >= 65:
            appearance_bonus = round(wage * random.uniform(0.01, 0.05), 2)
        if player.position in ("ST", "CF", "CAM", "LW", "RW"):
            goal_bonus = round(wage * random.uniform(0.02, 0.08), 2)
            assist_bonus = round(wage * random.uniform(0.01, 0.04), 2)
        if player.position == "GK":
            clean_sheet_bonus = round(wage * random.uniform(0.03, 0.1), 2)

        # Sell-on clause: usually for younger/cheaper transfers
        sell_on_pct = 0.0
        if age <= 24 and random.random() < 0.3:
            sell_on_pct = round(random.uniform(5.0, 25.0), 1)

        # Agent fee
        agent_fee_pct = round(random.uniform(3.0, 12.0), 1)

        # Squad role promised
        squad_role_promised = player.squad_role if player.squad_role != "not_set" else None

        contract = Contract(
            player_id=player.id,
            club_id=club.id,
            wage_per_week=wage,
            start_year=start_year,
            end_year=end_year,
            signing_bonus=signing_bonus,
            loyalty_bonus=loyalty_bonus,
            release_clause=release_clause,
            release_clause_foreign=release_clause_foreign,
            appearance_bonus=appearance_bonus,
            goal_bonus=goal_bonus,
            assist_bonus=assist_bonus,
            clean_sheet_bonus=clean_sheet_bonus,
            sell_on_clause_pct=sell_on_pct,
            agent_fee_pct=agent_fee_pct,
            squad_role_promised=squad_role_promised,
            is_active=True,
        )
        session.add(contract)
        count += 1

        if count % 500 == 0:
            session.flush()

    session.flush()
    print(f"[Ingestion] Created {count} contracts")
    return count


# ── Board expectations ────────────────────────────────────────────────────

def _generate_board_expectations(session) -> int:
    """Create BoardExpectation for each club based on tier/reputation."""
    clubs = session.query(Club).all()
    count = 0

    for club in clubs:
        existing = session.query(BoardExpectation).filter_by(club_id=club.id).first()
        if existing:
            continue

        rep = club.reputation or 50
        league = session.query(League).get(club.league_id) if club.league_id else None
        tier = league.tier if league else 2
        num_teams = league.num_teams if league else 20

        # Determine expected league position range based on reputation
        # Higher rep = higher expectations (lower position number)
        if rep >= 85:
            min_pos, max_pos = 1, 4
        elif rep >= 70:
            min_pos, max_pos = 1, 8
        elif rep >= 55:
            min_pos, max_pos = 5, 14
        elif rep >= 40:
            min_pos, max_pos = 8, max(num_teams - 2, 10)
        elif rep >= 25:
            min_pos, max_pos = max(num_teams // 2, 6), num_teams
        else:
            min_pos, max_pos = max(num_teams - 5, 10), num_teams

        # Clamp to league size
        min_pos = max(1, min(min_pos, num_teams))
        max_pos = max(min_pos, min(max_pos, num_teams))

        # Board confidence starts higher for better clubs
        confidence = max(40.0, min(85.0, 50.0 + rep * 0.3 + random.uniform(-5, 5)))

        # Fan happiness
        fan_happiness = max(40.0, min(80.0, 55.0 + rep * 0.2 + random.uniform(-5, 5)))

        # Patience: richer/bigger clubs have less patience
        if rep >= 75:
            patience = random.randint(2, 4)
        elif rep >= 50:
            patience = random.randint(3, 5)
        else:
            patience = random.randint(4, 7)

        # Style expectation based on tier/reputation
        if rep >= 75:
            style = random.choice(["attacking", "possession", "balanced"])
        elif rep >= 50:
            style = random.choice(["balanced", "possession", "counter_attack"])
        else:
            style = random.choice(["balanced", "defensive", "counter_attack"])

        # Board type
        if rep >= 80 and random.random() < 0.2:
            board_type = "sugar_daddy"
        elif rep <= 30 or (tier >= 3):
            board_type = random.choice(["balanced", "austere", "austere"])
        else:
            board_type = "balanced"

        # Also set club's board_type field
        club.board_type = board_type

        be = BoardExpectation(
            club_id=club.id,
            season=STARTING_SEASON,
            min_league_position=min_pos,
            max_league_position=max_pos,
            board_confidence=confidence,
            fan_happiness=fan_happiness,
            patience=patience,
            style_expectation=style,
        )
        session.add(be)
        count += 1

    session.flush()
    print(f"[Ingestion] Created {count} board expectations")
    return count


# ── Club facility fields ──────────────────────────────────────────────────

def _populate_club_facilities(session):
    """Populate new club facility/infrastructure columns based on reputation and tier."""
    clubs = session.query(Club).all()

    for club in clubs:
        rep = club.reputation or 50
        league = session.query(League).get(club.league_id) if club.league_id else None
        tier = league.tier if league else 2

        # facilities_level: 1-10, driven by reputation
        club.facilities_level = _clamp(
            int(rep / 10) + random.randint(-1, 1), lo=1, hi=10)

        # youth_academy_level: reputation-based with some variance
        club.youth_academy_level = _clamp(
            int(rep / 12) + random.randint(-1, 2), lo=1, hi=10)

        # training_facility_level: closely tied to club wealth
        club.training_facility_level = _clamp(
            int(rep / 11) + random.randint(-1, 1), lo=1, hi=10)

        # scouting_network_level: tier 1 clubs invest more in scouting
        base_scout = int(rep / 14) + (2 if tier == 1 else 0)
        club.scouting_network_level = _clamp(
            base_scout + random.randint(-1, 1), lo=1, hi=10)

        # medical_facility_level: tied to reputation
        club.medical_facility_level = _clamp(
            int(rep / 11) + random.randint(-1, 1), lo=1, hi=10)

        # Compute total weekly wages from player wages
        players = session.query(Player).filter_by(club_id=club.id).all()
        total_wages = sum(p.wage or 0.0 for p in players)
        club.total_wages = total_wages

    session.flush()
    print(f"[Ingestion] Populated facility levels for {len(clubs)} clubs")


def _generate_all_fixtures(session, leagues: list[League]) -> int:
    """Generate round-robin fixtures for every league."""
    total = 0
    for league in leagues:
        clubs = session.query(Club).filter_by(league_id=league.id).all()
        if len(clubs) < 2:
            continue

        # Trim to league.num_teams if we have too many clubs
        if len(clubs) > league.num_teams:
            clubs.sort(key=lambda c: c.reputation or 0, reverse=True)
            clubs = clubs[:league.num_teams]

        club_ids = [c.id for c in clubs]
        schedule = round_robin_schedule(club_ids)

        for matchday_idx, matchday in enumerate(schedule, start=1):
            for home_id, away_id in matchday:
                fixture = Fixture(
                    league_id=league.id,
                    season=STARTING_SEASON,
                    matchday=matchday_idx,
                    home_club_id=home_id,
                    away_club_id=away_id,
                )
                session.add(fixture)
                total += 1

        session.flush()
    return total


def _init_standings(session, leagues: list[League]):
    """Create initial league standing rows."""
    for league in leagues:
        clubs = session.query(Club).filter_by(league_id=league.id).all()
        for club in clubs:
            existing = session.query(LeagueStanding).filter_by(
                league_id=league.id, club_id=club.id, season=STARTING_SEASON
            ).first()
            if not existing:
                standing = LeagueStanding(
                    league_id=league.id,
                    club_id=club.id,
                    season=STARTING_SEASON,
                )
                session.add(standing)
    session.flush()


def _init_season(session):
    """Create the Season record."""
    existing = session.query(Season).filter_by(year=STARTING_SEASON).first()
    if not existing:
        season = Season(
            year=STARTING_SEASON,
            current_matchday=0,
            phase="pre_season",
        )
        session.add(season)
        session.flush()
