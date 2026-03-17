"""Game configuration constants and defaults."""
from pathlib import Path
import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SAVE_DIR = PROJECT_ROOT / "saves"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DB_NAME = "football_manager.db"

# ---------------------------------------------------------------------------
# GPU / Computation
# ---------------------------------------------------------------------------
def _detect_gpu() -> bool:
    """Return True when CuPy is available and at least one CUDA device exists."""
    try:
        import cupy as cp  # noqa: F401
        cp.cuda.runtime.getDeviceCount()
        return True
    except Exception:
        return False

USE_CUDA: bool = _detect_gpu()

# Numpy-compatible array module – CuPy on GPU, NumPy on CPU
def get_array_module():
    """Return cupy if CUDA is available, else numpy."""
    if USE_CUDA:
        import cupy as cp
        return cp
    import numpy as np
    return np

# ---------------------------------------------------------------------------
# Season / Calendar
# ---------------------------------------------------------------------------
STARTING_SEASON = 2024
SEASON_START_MONTH = 8   # August
SEASON_END_MONTH = 5     # May

# ---------------------------------------------------------------------------
# Match Engine
# ---------------------------------------------------------------------------
TICKS_PER_MINUTE = 3          # simulation resolution
MATCH_MINUTES = 90
TOTAL_TICKS = TICKS_PER_MINUTE * MATCH_MINUTES  # 270
SCORECARD_INTERVAL = 10       # minutes between scorecards

# Fatigue
FATIGUE_PER_MINUTE = 0.75      # out of 100 stamina
FATIGUE_SPRINT_COST = 0.4     # extra per sprint action
INJURY_BASE_CHANCE = 0.00008  # significantly lowered for realistic frequency (~0.3 injuries/game)

# ---------------------------------------------------------------------------
# Pitch zones (3 rows × 6 cols)
# ---------------------------------------------------------------------------
PITCH_ROWS = 3    # Left channel, Central, Right channel
PITCH_COLS = 6    # GK area, Defense, Deep midfield, Midfield, Attack, Final third

# ---------------------------------------------------------------------------
# Tactical defaults
# ---------------------------------------------------------------------------
DEFAULT_FORMATION = "4-4-2"
MENTALITY_LEVELS = ["very_defensive", "defensive", "cautious", "balanced",
                    "positive", "attacking", "very_attacking"]
TEMPO_LEVELS = ["very_slow", "slow", "normal", "fast", "very_fast"]
PRESSING_LEVELS = ["low", "standard", "high", "very_high"]
PASSING_STYLES = ["very_short", "short", "mixed", "direct", "very_direct"]
WIDTH_LEVELS = ["very_narrow", "narrow", "normal", "wide", "very_wide"]
DEFENSIVE_LINE_LEVELS = ["deep", "normal", "high"]

# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------
POSITIONS = [
    "GK", "CB", "LB", "RB", "LWB", "RWB",
    "CDM", "CM", "CAM", "LM", "RM",
    "LW", "RW", "CF", "ST",
]

# ---------------------------------------------------------------------------
# Leagues (Top 5 + second tiers)
# ---------------------------------------------------------------------------
LEAGUES_CONFIG = [
    {"name": "Premier League",      "country": "England",     "tier": 1, "num_teams": 20, "promo": 0, "releg": 3},
    {"name": "Championship",        "country": "England",     "tier": 2, "num_teams": 24, "promo": 3, "releg": 3},
    {"name": "League One",          "country": "England",     "tier": 3, "num_teams": 24, "promo": 3, "releg": 4},
    {"name": "League Two",          "country": "England",     "tier": 4, "num_teams": 24, "promo": 4, "releg": 2},
    {"name": "La Liga",             "country": "Spain",       "tier": 1, "num_teams": 20, "promo": 0, "releg": 3},
    {"name": "La Liga 2",           "country": "Spain",       "tier": 2, "num_teams": 22, "promo": 3, "releg": 3},
    {"name": "Bundesliga",          "country": "Germany",     "tier": 1, "num_teams": 18, "promo": 0, "releg": 2},
    {"name": "2. Bundesliga",       "country": "Germany",     "tier": 2, "num_teams": 18, "promo": 2, "releg": 2},
    {"name": "3. Liga",             "country": "Germany",     "tier": 3, "num_teams": 20, "promo": 2, "releg": 4},
    {"name": "Serie A",             "country": "Italy",       "tier": 1, "num_teams": 20, "promo": 0, "releg": 3},
    {"name": "Serie B",             "country": "Italy",       "tier": 2, "num_teams": 20, "promo": 3, "releg": 4},
    {"name": "Ligue 1",             "country": "France",      "tier": 1, "num_teams": 18, "promo": 0, "releg": 2},
    {"name": "Ligue 2",             "country": "France",      "tier": 2, "num_teams": 20, "promo": 2, "releg": 4},
    {"name": "Liga Portugal",       "country": "Portugal",    "tier": 1, "num_teams": 18, "promo": 0, "releg": 2},
    {"name": "Eredivisie",          "country": "Netherlands", "tier": 1, "num_teams": 18, "promo": 0, "releg": 2},
    {"name": "Premiership",         "country": "Scotland",    "tier": 1, "num_teams": 12, "promo": 0, "releg": 1},
    {"name": "Super Lig",           "country": "Turkey",      "tier": 1, "num_teams": 20, "promo": 0, "releg": 4},
    {"name": "Major League Soccer", "country": "USA",         "tier": 1, "num_teams": 29, "promo": 0, "releg": 0},
]

# ---------------------------------------------------------------------------
# Domestic Cups
# ---------------------------------------------------------------------------
CUPS_CONFIG = [
    {"name": "FA Cup", "country": "England"},
    {"name": "Copa del Rey", "country": "Spain"},
    {"name": "DFB-Pokal", "country": "Germany"},
    {"name": "Coppa Italia", "country": "Italy"},
    {"name": "Coupe de France", "country": "France"},
]

# ---------------------------------------------------------------------------
# Finance defaults (in millions €)
# ---------------------------------------------------------------------------
TIER1_BASE_BUDGET = 50.0
TIER2_BASE_BUDGET = 10.0
TV_MONEY_TIER1 = 80.0
TV_MONEY_TIER2 = 15.0

# ---------------------------------------------------------------------------
# AI Manager
# ---------------------------------------------------------------------------
AI_STYLES = ["attacking", "defensive", "balanced", "pragmatic",
             "possession", "counter_attack"]

# ---------------------------------------------------------------------------
# Advanced Match Engine V2
# ---------------------------------------------------------------------------
USE_ADVANCED_ENGINE = True        # Use V2 match engine by default
USE_V3_ENGINE = True              # Use V3 Markov chain match engine
MAX_POSSESSION_CHAIN = 15        # slightly longer chains for professional build-up
CHAINS_PER_MINUTE = 3.5          # realistic pace
THROUGH_BALL_OFFSIDE_RISK = 0.08 # lower base risk for elite players
COUNTER_ATTACK_THRESHOLD = 0.22  # slightly more dynamic counter-attacks

# ---------------------------------------------------------------------------
# Player Development
# ---------------------------------------------------------------------------
GROWTH_CHECK_INTERVAL = 4        # matchdays between development checks
RETIREMENT_MIN_AGE = 33
RETIREMENT_MAX_AGE = 40
INJURY_SEVERITY = {
    "minor": (1, 2),    # weeks
    "moderate": (3, 6),
    "serious": (7, 12),
    "career_threatening": (16, 40),
}
YELLOW_CARD_BAN_THRESHOLD = 5    # yellows before 1-match ban
YELLOW_CARD_BAN_THRESHOLD_2 = 10 # yellows before 2-match ban

# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------
TRAINING_SESSIONS_PER_WEEK = 5
PRE_SEASON_WEEKS = 6
MAX_TRAINING_INTENSITY = 5       # 1=recovery, 5=double
OVERTRAINING_RISK_THRESHOLD = 3  # intense sessions per week before injury risk spikes

# ---------------------------------------------------------------------------
# Scouting
# ---------------------------------------------------------------------------
SCOUT_KNOWLEDGE_PER_WEEK = {
    "player": 15.0,    # base knowledge gain per week (modified by scout quality)
    "club": 8.0,
    "region": 5.0,
}
MAX_SCOUT_ASSIGNMENTS = 3        # max concurrent assignments per scout
KNOWLEDGE_DECAY_PER_SEASON = 10  # knowledge decays if not refreshed

# ---------------------------------------------------------------------------
# Transfers & Contracts
# ---------------------------------------------------------------------------
TRANSFER_WINDOW_SUMMER_START = 1  # matchday in season
TRANSFER_WINDOW_SUMMER_END = 8
TRANSFER_WINDOW_WINTER_START = 19 # mid-season
TRANSFER_WINDOW_WINTER_END = 21
MAX_SQUAD_SIZE = 25
MIN_SQUAD_SIZE = 17
AGENT_FEE_MIN_PCT = 3.0
AGENT_FEE_MAX_PCT = 15.0
HOMEGROWN_REQUIREMENT = 8        # min homegrown players in 25-man squad

# ---------------------------------------------------------------------------
# Board & Fans
# ---------------------------------------------------------------------------
BOARD_PATIENCE = {
    "sugar_daddy": 10,   # matchdays of bad results before pressure
    "balanced": 6,
    "frugal": 8,
    "selling": 7,
}
SACKING_CONFIDENCE_THRESHOLD = 10  # board confidence below this = sacked
WARNING_CONFIDENCE_THRESHOLD = 25

# ---------------------------------------------------------------------------
# Youth Academy
# ---------------------------------------------------------------------------
YOUTH_INTAKE_MIN = 5
YOUTH_INTAKE_MAX = 15
YOUTH_MIN_AGE = 15
YOUTH_MAX_AGE = 17

# ---------------------------------------------------------------------------
# Financial Constants
# ---------------------------------------------------------------------------
TICKET_PRICE_BASE = 35           # euros
HOSPITALITY_MULTIPLIER = 8.0     # hospitality costs 8x normal ticket
HOSPITALITY_SEATS_PCT = 0.05     # 5% of stadium is hospitality
MERCHANDISE_BASE_PER_FAN = 15.0  # annual merchandise per fan base unit
PRIZE_MONEY_TIER1 = {
    1: 40.0, 2: 30.0, 3: 25.0, 4: 20.0, 5: 18.0,
    6: 15.0, 7: 13.0, 8: 11.0, 9: 10.0, 10: 9.0,
    11: 8.0, 12: 7.5, 13: 7.0, 14: 6.5, 15: 6.0,
    16: 5.5, 17: 5.0, 18: 4.5, 19: 4.0, 20: 3.5,
}  # millions by position
WAGE_TO_REVENUE_HEALTHY = 0.60   # healthy wage ratio
WAGE_TO_REVENUE_WARNING = 0.70   # warning level
WAGE_TO_REVENUE_CRITICAL = 0.85  # financial trouble

# ---------------------------------------------------------------------------
# Player Personality Types
# ---------------------------------------------------------------------------
PERSONALITY_TYPES = [
    "model_professional", "fairly_professional", "casual",
    "ambitious", "temperamental", "resolute", "spirited",
    "balanced", "loyal", "mercenary", "perfectionist",
]

# ---------------------------------------------------------------------------
# Player Roles (for tactical system)
# ---------------------------------------------------------------------------
PLAYER_ROLES = {
    "GK": ["goalkeeper", "sweeper_keeper"],
    "CB": ["central_defender", "ball_playing_defender", "no_nonsense_defender", "libero"],
    "LB": ["full_back", "wing_back", "inverted_wing_back"],
    "RB": ["full_back", "wing_back", "inverted_wing_back"],
    "CDM": ["defensive_midfielder", "ball_winning_midfielder", "half_back", "regista"],
    "CM": ["central_midfielder", "box_to_box", "deep_lying_playmaker", "mezzala", "carrilero"],
    "CAM": ["advanced_playmaker", "trequartista", "enganche", "shadow_striker"],
    "LM": ["wide_midfielder", "inside_forward", "winger"],
    "RM": ["wide_midfielder", "inside_forward", "winger"],
    "LW": ["winger", "inside_forward", "inverted_winger", "raumdeuter"],
    "RW": ["winger", "inside_forward", "inverted_winger", "raumdeuter"],
    "CF": ["deep_lying_forward", "false_nine", "target_man", "pressing_forward"],
    "ST": ["advanced_forward", "poacher", "complete_forward", "target_man", "pressing_forward"],
}

# ---------------------------------------------------------------------------
# Regions for Scouting
# ---------------------------------------------------------------------------
SCOUTING_REGIONS = [
    "England", "Spain", "Germany", "Italy", "France",
    "Portugal", "Netherlands", "Belgium", "South America",
    "Central America", "North America", "Scandinavia",
    "Eastern Europe", "Balkans", "Turkey", "Africa",
    "East Asia", "Southeast Asia", "Middle East", "Oceania",
]

# ---------------------------------------------------------------------------
# Staff Defaults
# ---------------------------------------------------------------------------
STAFF_WAGE_MULTIPLIER = {
    "head_coach": 1.0,
    "assistant": 0.6,
    "gk_coach": 0.4,
    "fitness_coach": 0.4,
    "scout": 0.3,
    "chief_scout": 0.5,
    "physio": 0.35,
    "analyst": 0.3,
    "youth_coach": 0.4,
    "set_piece_coach": 0.35,
}
