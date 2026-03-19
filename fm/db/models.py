"""SQLAlchemy ORM models for every game entity."""
from __future__ import annotations

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey, Text, Enum as SAEnum,
    UniqueConstraint, CheckConstraint, create_engine,
)
from sqlalchemy.orm import declarative_base, relationship
import enum

Base = declarative_base()

# ── Enums ──────────────────────────────────────────────────────────────────


class Position(str, enum.Enum):
    GK = "GK"
    CB = "CB"
    LB = "LB"
    RB = "RB"
    LWB = "LWB"
    RWB = "RWB"
    CDM = "CDM"
    CM = "CM"
    CAM = "CAM"
    LM = "LM"
    RM = "RM"
    LW = "LW"
    RW = "RW"
    CF = "CF"
    ST = "ST"


class EventType(str, enum.Enum):
    GOAL = "goal"
    OWN_GOAL = "own_goal"
    ASSIST = "assist"
    SHOT = "shot"
    SHOT_ON_TARGET = "shot_on_target"
    SAVE = "save"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    FOUL = "foul"
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"
    SUBSTITUTION = "substitution"
    INJURY = "injury"
    CORNER = "corner"
    FREE_KICK = "free_kick"
    PENALTY = "penalty"
    OFFSIDE = "offside"


class SeasonPhase(str, enum.Enum):
    PRE_SEASON = "pre_season"
    TRANSFER_WINDOW = "transfer_window"
    IN_SEASON = "in_season"
    MID_SEASON_BREAK = "mid_season_break"
    END_OF_SEASON = "end_of_season"


class NewsCategory(str, enum.Enum):
    TRANSFER = "transfer"
    MATCH = "match"
    INJURY = "injury"
    MANAGER = "manager"
    FINANCE = "finance"
    GENERAL = "general"
    AWARD = "award"
    CUP = "cup"
    CONTINENTAL = "continental"


class TrainingFocusEnum(str, enum.Enum):
    ATTACKING = "attacking"
    DEFENDING = "defending"
    PHYSICAL = "physical"
    TACTICAL = "tactical"
    SET_PIECES = "set_pieces"
    MATCH_PREP = "match_prep"


class TeamTalkTypeEnum(str, enum.Enum):
    MOTIVATE = "motivate"
    CALM = "calm"
    PRAISE = "praise"
    CRITICIZE = "criticize"
    FOCUS = "focus"
    NO_PRESSURE = "no_pressure"


# ── Models ─────────────────────────────────────────────────────────────────


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    country = Column(String(60), nullable=False)
    tier = Column(Integer, nullable=False, default=1)
    num_teams = Column(Integer, nullable=False)
    promotion_spots = Column(Integer, nullable=False, default=0)
    relegation_spots = Column(Integer, nullable=False, default=3)

    clubs = relationship("Club", back_populates="league")
    fixtures = relationship("Fixture", back_populates="league")
    standings = relationship("LeagueStanding", back_populates="league")


class Club(Base):
    __tablename__ = "clubs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    short_name = Column(String(30))
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=True)
    reputation = Column(Integer, default=50)          # 1-100
    budget = Column(Float, default=0.0)               # millions EUR
    wage_budget = Column(Float, default=0.0)          # weekly wages budget
    total_wages = Column(Float, default=0.0)          # current weekly wage bill
    facilities_level = Column(Integer, default=5)     # 1-10
    stadium_capacity = Column(Integer, default=30000)
    primary_color = Column(String(7), default="#FFFFFF")
    secondary_color = Column(String(7), default="#000000")
    training_focus = Column(String(20), default="match_prep")

    # ── New facility / infrastructure columns ──
    youth_academy_level = Column(Integer, default=5)        # 1-10
    training_facility_level = Column(Integer, default=5)    # 1-10
    scouting_network_level = Column(Integer, default=3)     # 1-10
    medical_facility_level = Column(Integer, default=5)     # 1-10
    stadium_name = Column(String(120), nullable=True)
    board_type = Column(String(30), default="balanced")     # sugar_daddy, balanced, austere

    # ── V3: Team spirit ──
    team_spirit = Column(Float, default=60.0)               # 0-100

    league = relationship("League", back_populates="clubs")
    players = relationship("Player", back_populates="club", foreign_keys="Player.club_id")
    manager = relationship("Manager", back_populates="club", uselist=False)
    tactical_setup = relationship("TacticalSetup", back_populates="club", uselist=False)
    home_fixtures = relationship(
        "Fixture", back_populates="home_club", foreign_keys="Fixture.home_club_id",
    )
    away_fixtures = relationship(
        "Fixture", back_populates="away_club", foreign_keys="Fixture.away_club_id",
    )
    standings = relationship("LeagueStanding", back_populates="club")
    staff = relationship("Staff", back_populates="club")
    contracts = relationship("Contract", back_populates="club", foreign_keys="Contract.club_id")
    board_expectation = relationship("BoardExpectation", back_populates="club", uselist=False)
    training_schedules = relationship("TrainingSchedule", back_populates="club", foreign_keys="TrainingSchedule.club_id")
    youth_candidates = relationship("YouthCandidate", back_populates="club")


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    short_name = Column(String(60))
    age = Column(Integer, nullable=False)
    nationality = Column(String(60))
    position = Column(String(5), nullable=False)           # primary position
    secondary_positions = Column(String(30), default="")   # comma-separated
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    contract_expiry = Column(Integer, default=2026)        # year
    wage = Column(Float, default=0.0)                      # weekly wage EUR
    market_value = Column(Float, default=0.0)              # millions EUR

    # ── Loan tracking ──
    is_loan = Column(Boolean, default=False)
    loan_from_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)

    # ── Overall ──
    overall = Column(Integer, default=50)
    potential = Column(Integer, default=50)

    # ── Technical attributes (1-99) ──
    pace = Column(Integer, default=50)
    acceleration = Column(Integer, default=50)
    sprint_speed = Column(Integer, default=50)
    shooting = Column(Integer, default=50)
    finishing = Column(Integer, default=50)
    shot_power = Column(Integer, default=50)
    long_shots = Column(Integer, default=50)
    volleys = Column(Integer, default=50)
    penalties = Column(Integer, default=50)
    passing = Column(Integer, default=50)
    vision = Column(Integer, default=50)
    crossing = Column(Integer, default=50)
    free_kick_accuracy = Column(Integer, default=50)
    short_passing = Column(Integer, default=50)
    long_passing = Column(Integer, default=50)
    curve = Column(Integer, default=50)
    dribbling = Column(Integer, default=50)
    agility = Column(Integer, default=50)
    balance = Column(Integer, default=50)
    ball_control = Column(Integer, default=50)
    defending = Column(Integer, default=50)
    marking = Column(Integer, default=50)
    standing_tackle = Column(Integer, default=50)
    sliding_tackle = Column(Integer, default=50)
    interceptions = Column(Integer, default=50)
    heading_accuracy = Column(Integer, default=50)
    physical = Column(Integer, default=50)
    stamina = Column(Integer, default=50)
    strength = Column(Integer, default=50)
    jumping = Column(Integer, default=50)
    aggression = Column(Integer, default=50)

    # ── Mental attributes ──
    composure = Column(Integer, default=50)
    reactions = Column(Integer, default=50)
    positioning = Column(Integer, default=50)
    att_work_rate = Column(String(10), default="medium")   # low/medium/high
    def_work_rate = Column(String(10), default="medium")

    # ── GK-specific (1-99, relevant only for GKs) ──
    gk_diving = Column(Integer, default=10)
    gk_handling = Column(Integer, default=10)
    gk_kicking = Column(Integer, default=10)
    gk_positioning = Column(Integer, default=10)
    gk_reflexes = Column(Integer, default=10)
    gk_speed = Column(Integer, default=10)

    # ── Hidden attributes (derived during ingestion) ──
    consistency = Column(Integer, default=65)          # 1-99
    injury_proneness = Column(Integer, default=30)     # 1-99 (higher = more prone)
    big_match = Column(Integer, default=65)            # 1-99

    # ── Personality / mental character (1-99) ──
    leadership = Column(Integer, default=50)
    teamwork = Column(Integer, default=50)
    determination = Column(Integer, default=50)
    ambition = Column(Integer, default=50)
    loyalty = Column(Integer, default=50)
    temperament = Column(Integer, default=50)
    professionalism = Column(Integer, default=50)
    pressure_handling = Column(Integer, default=50)
    adaptability = Column(Integer, default=50)
    versatility = Column(Integer, default=50)
    dirtiness = Column(Integer, default=50)
    flair = Column(Integer, default=50)
    important_matches = Column(Integer, default=50)

    # ── Physical profile ──
    height_cm = Column(Integer, default=180)
    weight_kg = Column(Integer, default=75)
    preferred_foot = Column(String(10), default="right")   # right / left / both
    weak_foot_ability = Column(Integer, default=2)         # 1-5

    # ── Traits (JSON list, e.g. '["Finesse Shot","Power Header"]') ──
    traits = Column(Text, nullable=True)

    # ── Ability ratings ──
    current_ability = Column(Integer, default=100)     # 1-200 internal scale
    potential_ability = Column(Integer, default=120)   # 1-200 internal scale

    # ── Happiness / transfer desire ──
    happiness = Column(Float, default=65.0)            # 0-100
    loyalty_to_manager = Column(Float, default=50.0)   # 0-100
    wants_transfer = Column(Boolean, default=False)
    release_clause = Column(Float, nullable=True)      # millions EUR
    squad_role = Column(String(20), default="not_set")

    # ── V3: Consequence system ──
    trust_in_manager = Column(Float, default=60.0)     # 0-100
    consecutive_benched = Column(Integer, default=0)    # matchdays benched in a row
    fan_favorite = Column(Boolean, default=False)       # marked by fan popularity
    # squad_role values: star_player, first_team, rotation, backup, youth, not_set

    # ── Match readiness ──
    match_sharpness = Column(Float, default=70.0)      # 0-100
    tactical_familiarity = Column(Float, default=50.0)  # 0-100
    team_chemistry = Column(Float, default=50.0)       # 0-100

    # ── Season accumulators ──
    goals_season = Column(Integer, default=0)
    assists_season = Column(Integer, default=0)
    minutes_season = Column(Integer, default=0)

    # ── Dynamic state (changes during game) ──
    fitness = Column(Float, default=100.0)             # 0-100
    morale = Column(Float, default=65.0)               # 0-100
    form = Column(Float, default=65.0)                 # 0-100, rolling average
    injured_weeks = Column(Integer, default=0)
    suspended_matches = Column(Integer, default=0)
    yellow_cards_season = Column(Integer, default=0)
    red_cards_season = Column(Integer, default=0)

    club = relationship("Club", back_populates="players", foreign_keys=[club_id])
    stats = relationship("PlayerStats", back_populates="player")
    events = relationship(
        "MatchEvent", back_populates="player", foreign_keys="MatchEvent.player_id",
    )
    match_stats = relationship("PlayerMatchStats", back_populates="player")
    contracts = relationship("Contract", back_populates="player")
    instructions = relationship("PlayerInstruction", back_populates="player")


class Manager(Base):
    __tablename__ = "managers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True, unique=True)
    is_human = Column(Boolean, default=False)
    tactical_style = Column(String(30), default="balanced")
    reputation = Column(Integer, default=50)
    preferred_formation = Column(String(10), default="4-4-2")

    # ── Manager skills (1-99) ──
    tactical_knowledge = Column(Integer, default=50)
    man_management = Column(Integer, default=50)
    motivation_skill = Column(Integer, default=50)
    discipline_rating = Column(Integer, default=50)
    youth_development = Column(Integer, default=50)

    # ── Career record ──
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)

    club = relationship("Club", back_populates="manager")


class TacticalSetup(Base):
    __tablename__ = "tactical_setups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False, unique=True)
    formation = Column(String(10), default="4-4-2")
    mentality = Column(String(20), default="balanced")
    tempo = Column(String(15), default="normal")
    width = Column(String(15), default="normal")
    pressing = Column(String(15), default="standard")
    passing_style = Column(String(15), default="mixed")
    defensive_line = Column(String(15), default="normal")      # deep/normal/high
    creative_freedom = Column(String(15), default="normal")

    # ── Advanced tactical options ──
    offside_trap = Column(Boolean, default=False)
    counter_attack = Column(Boolean, default=False)
    play_out_from_back = Column(Boolean, default=False)
    time_wasting = Column(String(10), default="off")           # off / sometimes / always

    # ── Set-piece / captain assignments (FK to players) ──
    penalty_taker_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    corner_taker_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    free_kick_taker_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    captain_id = Column(Integer, ForeignKey("players.id"), nullable=True)

    # ── In-match plan adjustments ──
    match_plan_winning = Column(String(20), default="hold_lead")
    # hold_lead, push_for_more, time_waste, park_the_bus
    match_plan_losing = Column(String(20), default="push_forward")
    # push_forward, all_out_attack, stay_calm, long_balls
    match_plan_drawing = Column(String(20), default="stay_balanced")
    # stay_balanced, push_forward, tighten_up

    club = relationship("Club", back_populates="tactical_setup")
    player_instructions = relationship("PlayerInstruction", back_populates="tactical_setup")
    penalty_taker = relationship("Player", foreign_keys=[penalty_taker_id])
    corner_taker = relationship("Player", foreign_keys=[corner_taker_id])
    free_kick_taker = relationship("Player", foreign_keys=[free_kick_taker_id])
    captain = relationship("Player", foreign_keys=[captain_id])


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=False)
    season = Column(Integer, nullable=False)
    matchday = Column(Integer, nullable=False)
    home_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    away_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)
    played = Column(Boolean, default=False)

    # Match stats (stored after simulation)
    home_possession = Column(Float, nullable=True)
    home_shots = Column(Integer, nullable=True)
    home_shots_on_target = Column(Integer, nullable=True)
    away_shots = Column(Integer, nullable=True)
    away_shots_on_target = Column(Integer, nullable=True)
    home_xg = Column(Float, nullable=True)
    away_xg = Column(Float, nullable=True)

    # Extended match stats
    home_passes = Column(Integer, nullable=True)
    home_passes_completed = Column(Integer, nullable=True)
    away_passes = Column(Integer, nullable=True)
    away_passes_completed = Column(Integer, nullable=True)
    home_tackles = Column(Integer, nullable=True)
    home_tackles_won = Column(Integer, nullable=True)
    away_tackles = Column(Integer, nullable=True)
    away_tackles_won = Column(Integer, nullable=True)
    home_interceptions = Column(Integer, nullable=True)
    away_interceptions = Column(Integer, nullable=True)
    home_corners = Column(Integer, nullable=True)
    away_corners = Column(Integer, nullable=True)
    home_fouls = Column(Integer, nullable=True)
    away_fouls = Column(Integer, nullable=True)
    home_offsides = Column(Integer, nullable=True)
    away_offsides = Column(Integer, nullable=True)
    home_yellow_cards = Column(Integer, nullable=True)
    away_yellow_cards = Column(Integer, nullable=True)
    home_red_cards = Column(Integer, nullable=True)
    away_red_cards = Column(Integer, nullable=True)
    home_saves = Column(Integer, nullable=True)
    away_saves = Column(Integer, nullable=True)
    home_clearances = Column(Integer, nullable=True)
    away_clearances = Column(Integer, nullable=True)
    home_crosses = Column(Integer, nullable=True)
    away_crosses = Column(Integer, nullable=True)
    home_dribbles_completed = Column(Integer, nullable=True)
    away_dribbles_completed = Column(Integer, nullable=True)
    home_aerials_won = Column(Integer, nullable=True)
    away_aerials_won = Column(Integer, nullable=True)
    home_big_chances = Column(Integer, nullable=True)
    away_big_chances = Column(Integer, nullable=True)
    home_key_passes = Column(Integer, nullable=True)
    away_key_passes = Column(Integer, nullable=True)

    # ── New match metadata ──
    attendance = Column(Integer, nullable=True)
    weather = Column(String(20), nullable=True)
    motm_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)

    # ── Tactical history (what each team played) ──
    home_formation = Column(String(10), nullable=True)
    home_mentality = Column(String(20), nullable=True)
    home_pressing = Column(String(15), nullable=True)
    home_tempo = Column(String(15), nullable=True)
    home_passing_style = Column(String(15), nullable=True)
    home_width = Column(String(15), nullable=True)
    home_defensive_line = Column(String(15), nullable=True)
    away_formation = Column(String(10), nullable=True)
    away_mentality = Column(String(20), nullable=True)
    away_pressing = Column(String(15), nullable=True)
    away_tempo = Column(String(15), nullable=True)
    away_passing_style = Column(String(15), nullable=True)
    away_width = Column(String(15), nullable=True)
    away_defensive_line = Column(String(15), nullable=True)

    league = relationship("League", back_populates="fixtures")
    home_club = relationship(
        "Club", back_populates="home_fixtures", foreign_keys=[home_club_id],
    )
    away_club = relationship(
        "Club", back_populates="away_fixtures", foreign_keys=[away_club_id],
    )
    events = relationship(
        "MatchEvent", back_populates="fixture", cascade="all, delete-orphan",
    )
    player_match_stats = relationship("PlayerMatchStats", back_populates="fixture")
    motm_player = relationship("Player", foreign_keys=[motm_player_id])


class MatchEvent(Base):
    __tablename__ = "match_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    minute = Column(Integer, nullable=False)
    event_type = Column(String(20), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    assist_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    zone_col = Column(Integer, nullable=True)
    zone_row = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    team_side = Column(String(4), nullable=True)  # home/away

    fixture = relationship("Fixture", back_populates="events")
    player = relationship(
        "Player", back_populates="events", foreign_keys=[player_id],
    )
    assist_player = relationship("Player", foreign_keys=[assist_player_id])


class LeagueStanding(Base):
    __tablename__ = "league_standings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    season = Column(Integer, nullable=False)
    played = Column(Integer, default=0)
    won = Column(Integer, default=0)
    drawn = Column(Integer, default=0)
    lost = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    goal_difference = Column(Integer, default=0)
    points = Column(Integer, default=0)
    form = Column(String(10), default="")  # last 5 results e.g. "WWDLW"

    __table_args__ = (
        UniqueConstraint("league_id", "club_id", "season", name="uq_standing"),
    )

    league = relationship("League", back_populates="standings")
    club = relationship("Club", back_populates="standings")


class PlayerStats(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    season = Column(Integer, nullable=False)
    appearances = Column(Integer, default=0)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    clean_sheets = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    minutes_played = Column(Integer, default=0)
    avg_rating = Column(Float, default=6.0)

    __table_args__ = (
        UniqueConstraint("player_id", "season", name="uq_player_season"),
    )

    player = relationship("Player", back_populates="stats")


class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False, unique=True)
    current_matchday = Column(Integer, default=0)
    phase = Column(String(20), default=SeasonPhase.PRE_SEASON.value)
    human_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)


class Transfer(Base):
    __tablename__ = "transfers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    from_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    to_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    fee = Column(Float, default=0.0)           # millions EUR
    wage = Column(Float, default=0.0)          # new weekly wage
    season = Column(Integer, nullable=False)
    is_loan = Column(Boolean, default=False)
    loan_end_season = Column(Integer, nullable=True)

    # ── Expanded transfer details ──
    transfer_type = Column(String(20), default="permanent")
    # permanent, loan, free, swap, release
    sell_on_clause_pct = Column(Float, default=0.0)
    agent_fee = Column(Float, default=0.0)          # millions EUR
    contract_years = Column(Integer, default=3)


class NewsItem(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season = Column(Integer, nullable=False)
    matchday = Column(Integer, nullable=True)
    headline = Column(String(200), nullable=False)
    body = Column(Text, nullable=True)
    category = Column(String(20), default=NewsCategory.GENERAL.value)
    is_read = Column(Boolean, default=False)


class CupFixture(Base):
    __tablename__ = "cup_fixtures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cup_name = Column(String(60), nullable=False)
    season = Column(Integer, nullable=False)
    round_number = Column(Integer, nullable=False)  # 1=first round, etc.
    home_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    away_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)
    extra_time = Column(Boolean, default=False)
    penalties = Column(Boolean, default=False)
    penalty_home = Column(Integer, nullable=True)
    penalty_away = Column(Integer, nullable=True)
    played = Column(Boolean, default=False)
    winner_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)

    home_club = relationship("Club", foreign_keys=[home_club_id])
    away_club = relationship("Club", foreign_keys=[away_club_id])
    winner_club = relationship("Club", foreign_keys=[winner_club_id])


# ── New Models ─────────────────────────────────────────────────────────────


class Staff(Base):
    """Club staff: coaches, scouts, physios, etc."""
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    role = Column(String(30), nullable=False)
    # role values: head_coach, assistant, gk_coach, fitness_coach, scout,
    #              physio, youth_coach, analyst, chief_scout
    nationality = Column(String(60), nullable=True)
    age = Column(Integer, default=40)

    # ── Coaching attributes (1-99) ──
    coaching_attacking = Column(Integer, default=50)
    coaching_defending = Column(Integer, default=50)
    coaching_tactical = Column(Integer, default=50)
    coaching_technical = Column(Integer, default=50)
    coaching_mental = Column(Integer, default=50)
    coaching_fitness = Column(Integer, default=50)
    coaching_gk = Column(Integer, default=50)

    # ── Scouting attributes ──
    scouting_ability = Column(Integer, default=50)
    scouting_potential_judge = Column(Integer, default=50)

    # ── Medical / sports science ──
    physiotherapy = Column(Integer, default=50)
    sports_science = Column(Integer, default=50)

    # ── Management style ──
    motivation = Column(Integer, default=50)
    discipline = Column(Integer, default=50)
    man_management = Column(Integer, default=50)

    # ── Contract ──
    wage = Column(Float, default=0.0)               # weekly wage
    contract_expiry = Column(Integer, default=2026)  # year
    reputation = Column(Integer, default=50)         # 1-100

    club = relationship("Club", back_populates="staff")
    scout_assignments = relationship("ScoutAssignment", back_populates="scout")


class Contract(Base):
    """Detailed player contract (separate from the wage column on Player)."""
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    wage_per_week = Column(Float, default=0.0)
    start_year = Column(Integer, nullable=False)
    end_year = Column(Integer, nullable=False)

    # ── Bonuses ──
    signing_bonus = Column(Float, nullable=True)
    loyalty_bonus = Column(Float, nullable=True)
    release_clause = Column(Float, nullable=True)           # millions EUR
    release_clause_foreign = Column(Float, nullable=True)   # foreign clubs only
    appearance_bonus = Column(Float, default=0.0)           # per appearance
    goal_bonus = Column(Float, default=0.0)
    assist_bonus = Column(Float, default=0.0)
    clean_sheet_bonus = Column(Float, default=0.0)

    # ── Agent / sell-on ──
    sell_on_clause_pct = Column(Float, default=0.0)   # 0-50%
    agent_fee_pct = Column(Float, default=5.0)        # % of transfer fee

    # ── Loan details ──
    is_loan = Column(Boolean, default=False)
    loan_from_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    optional_buy_clause = Column(Float, nullable=True)  # millions EUR

    # ── Promises ──
    squad_role_promised = Column(String(20), nullable=True)
    is_active = Column(Boolean, default=True)

    player = relationship("Player", back_populates="contracts")
    club = relationship("Club", back_populates="contracts", foreign_keys=[club_id])
    loan_from_club = relationship("Club", foreign_keys=[loan_from_club_id])


class TransferBid(Base):
    """A transfer bid from one club for a player."""
    __tablename__ = "transfer_bids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    bidding_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    selling_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)

    bid_amount = Column(Float, default=0.0)              # millions EUR
    offered_wage = Column(Float, default=0.0)            # weekly wage
    offered_contract_years = Column(Integer, default=3)

    status = Column(String(20), default="pending")
    # pending, accepted, rejected, countered, withdrawn, player_rejected
    counter_amount = Column(Float, nullable=True)

    season = Column(Integer, nullable=False)
    is_loan_bid = Column(Boolean, default=False)
    sell_on_pct = Column(Float, default=0.0)

    player = relationship("Player", foreign_keys=[player_id])
    bidding_club = relationship("Club", foreign_keys=[bidding_club_id])
    selling_club = relationship("Club", foreign_keys=[selling_club_id])


class ScoutAssignment(Base):
    """An active scouting assignment."""
    __tablename__ = "scout_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scout_id = Column(Integer, ForeignKey("staff.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    target_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    region = Column(String(60), nullable=True)

    started_matchday = Column(Integer, default=0)
    duration_weeks = Column(Integer, default=4)
    weeks_completed = Column(Integer, default=0)

    knowledge_pct = Column(Float, default=0.0)   # 0-100
    report_ready = Column(Boolean, default=False)
    season = Column(Integer, nullable=False)

    scout = relationship("Staff", back_populates="scout_assignments")
    player = relationship("Player", foreign_keys=[player_id])
    club = relationship("Club", foreign_keys=[club_id])
    target_club = relationship("Club", foreign_keys=[target_club_id])


class PlayerRelationship(Base):
    """Relationship between two players (e.g. friends, rivals)."""
    __tablename__ = "player_relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_a_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player_b_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    relationship_type = Column(String(30), nullable=False)
    # friends, close_friends, rivals, dislike, mentor, protege
    strength = Column(Float, default=50.0)  # 0-100

    player_a = relationship("Player", foreign_keys=[player_a_id])
    player_b = relationship("Player", foreign_keys=[player_b_id])


class BoardExpectation(Base):
    """Board expectations and confidence for a club."""
    __tablename__ = "board_expectations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False, unique=True)
    season = Column(Integer, nullable=False)

    min_league_position = Column(Integer, default=1)
    max_league_position = Column(Integer, default=20)

    board_confidence = Column(Float, default=60.0)   # 0-100
    fan_happiness = Column(Float, default=60.0)      # 0-100
    patience = Column(Integer, default=3)            # seasons of patience left
    style_expectation = Column(String(20), default="balanced")

    # ── V3: Board escalation ──
    warnings_issued = Column(Integer, default=0)
    ultimatum_active = Column(Boolean, default=False)
    transfer_embargo = Column(Boolean, default=False)
    # attacking, balanced, defensive, possession, counter_attack

    club = relationship("Club", back_populates="board_expectation")


class PlayerMatchStats(Base):
    """Detailed per-match statistics for a player."""
    __tablename__ = "player_match_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    season = Column(Integer, nullable=False)

    minutes_played = Column(Integer, default=0)
    rating = Column(Float, default=6.0)                # 1-10
    position_played = Column(String(5), nullable=True)

    # ── Attacking ──
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    shots = Column(Integer, default=0)
    shots_on_target = Column(Integer, default=0)
    key_passes = Column(Integer, default=0)
    through_balls = Column(Integer, default=0)

    # ── Passing ──
    passes_attempted = Column(Integer, default=0)
    passes_completed = Column(Integer, default=0)
    crosses_attempted = Column(Integer, default=0)
    crosses_completed = Column(Integer, default=0)

    # ── Dribbling / duels ──
    dribbles_attempted = Column(Integer, default=0)
    dribbles_completed = Column(Integer, default=0)
    tackles_attempted = Column(Integer, default=0)
    tackles_won = Column(Integer, default=0)
    interceptions = Column(Integer, default=0)
    clearances = Column(Integer, default=0)
    blocks = Column(Integer, default=0)

    # ── Aerial ──
    aerials_won = Column(Integer, default=0)
    aerials_lost = Column(Integer, default=0)

    # ── Discipline ──
    fouls_committed = Column(Integer, default=0)
    fouls_won = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_card = Column(Boolean, default=False)

    # ── GK ──
    saves = Column(Integer, default=0)
    clean_sheet = Column(Boolean, default=False)

    # ── Physical / advanced ──
    distance_covered_km = Column(Float, default=0.0)
    touches = Column(Integer, default=0)
    xg = Column(Float, default=0.0)
    xa = Column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("player_id", "fixture_id", name="uq_player_fixture"),
    )

    player = relationship("Player", back_populates="match_stats")
    fixture = relationship("Fixture", back_populates="player_match_stats")


class TrainingSchedule(Base):
    """Training schedule for a club or individual player."""
    __tablename__ = "training_schedules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)

    focus = Column(String(30), nullable=False)
    intensity = Column(String(15), default="normal")
    # recovery, light, normal, intense, double
    duration_weeks = Column(Integer, default=1)
    weeks_completed = Column(Integer, default=0)

    individual_attrs = Column(Text, nullable=True)
    # JSON list of specific attributes to train, e.g. '["finishing","composure"]'
    is_match_prep = Column(Boolean, default=False)
    opponent_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)

    club = relationship("Club", back_populates="training_schedules", foreign_keys=[club_id])
    player = relationship("Player", foreign_keys=[player_id])
    opponent = relationship("Club", foreign_keys=[opponent_id])


class YouthCandidate(Base):
    """A youth academy prospect not yet promoted to the first team."""
    __tablename__ = "youth_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    name = Column(String(120), nullable=False)
    age = Column(Integer, default=16)
    position = Column(String(5), nullable=False)
    nationality = Column(String(60), nullable=True)

    potential_min = Column(Integer, default=50)
    potential_max = Column(Integer, default=80)
    current_ability = Column(Integer, default=30)

    personality_type = Column(String(20), default="balanced")
    # balanced, determined, professional, lazy, volatile, perfectionist, spirited

    # ── Advanced Depth ──
    archetype = Column(String(30), nullable=True)
    consistency = Column(Integer, default=50)           # 1-99
    injury_proneness = Column(Integer, default=30)      # 1-99 (higher = more prone)
    important_matches = Column(Integer, default=50)     # 1-99
    loyalty = Column(Integer, default=50)               # 1-99
    pressure = Column(Integer, default=50)              # 1-99
    professionalism = Column(Integer, default=50)       # 1-99
    ambition = Column(Integer, default=50)              # 1-99
    determination = Column(Integer, default=50)         # 1-99

    ready_to_promote = Column(Boolean, default=False)
    season_joined = Column(Integer, default=0)

    club = relationship("Club", back_populates="youth_candidates")


class PlayerInstruction(Base):
    """Per-player tactical instructions within a formation."""
    __tablename__ = "player_instructions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tactical_setup_id = Column(Integer, ForeignKey("tactical_setups.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    position_in_formation = Column(String(10), nullable=False)
    role = Column(String(30), default="standard")
    # standard, advanced_playmaker, deep_lying_playmaker, ball_winning_midfielder,
    # target_man, poacher, trequartista, mezzala, regista, inverted_winger, etc.
    duty = Column(String(10), default="support")
    # defend, support, attack

    closing_down = Column(String(10), default="normal")   # low, normal, high
    tackling = Column(String(10), default="normal")        # easy, normal, hard
    passing_directness = Column(String(10), default="normal")  # short, normal, long

    hold_position = Column(Boolean, default=False)
    roam_from_position = Column(Boolean, default=False)

    tactical_setup = relationship("TacticalSetup", back_populates="player_instructions")
    player = relationship("Player", back_populates="instructions")


# ── Continental Competition Models ────────────────────────────────────────


class ContinentalGroup(Base):
    """Group-stage standing for a continental competition (CL, EL, ECL)."""
    __tablename__ = "continental_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competition_name = Column(String(60), nullable=False)   # "Champions League", etc.
    season = Column(Integer, nullable=False)
    group_letter = Column(String(1), nullable=False)         # A-H
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    pot = Column(Integer, default=1)                         # seeding pot 1-4

    played = Column(Integer, default=0)
    won = Column(Integer, default=0)
    drawn = Column(Integer, default=0)
    lost = Column(Integer, default=0)
    gf = Column(Integer, default=0)
    ga = Column(Integer, default=0)
    gd = Column(Integer, default=0)
    points = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint(
            "competition_name", "season", "group_letter", "club_id",
            name="uq_continental_group_entry",
        ),
    )

    club = relationship("Club", foreign_keys=[club_id])


class ContinentalFixture(Base):
    """Fixture for a continental competition (group stage or knockout)."""
    __tablename__ = "continental_fixtures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    competition_name = Column(String(60), nullable=False)
    season = Column(Integer, nullable=False)

    # Stage: "group", "r16", "qf", "sf", "final"
    stage = Column(String(10), nullable=False, default="group")
    group_letter = Column(String(1), nullable=True)          # NULL for knockouts
    leg = Column(Integer, default=1)                          # 1 or 2 (final = 1)
    matchday = Column(Integer, nullable=False)                # season matchday

    home_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    away_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    home_goals = Column(Integer, nullable=True)
    away_goals = Column(Integer, nullable=True)
    played = Column(Boolean, default=False)

    extra_time = Column(Boolean, default=False)
    penalties = Column(Boolean, default=False)
    penalty_home = Column(Integer, nullable=True)
    penalty_away = Column(Integer, nullable=True)

    # Aggregate tracking for knockout ties (filled after leg 2)
    aggregate_home = Column(Integer, nullable=True)
    aggregate_away = Column(Integer, nullable=True)

    # Winner (set for knockout ties after both legs, or after final)
    winner_club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)

    home_club = relationship("Club", foreign_keys=[home_club_id])
    away_club = relationship("Club", foreign_keys=[away_club_id])
    winner_club = relationship("Club", foreign_keys=[winner_club_id])

class Saga(Base):
    """Multi-matchday narrative state (e.g., transfer sagas, injury crises)."""
    __tablename__ = "sagas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(30), nullable=False) # transfer, injury, performance, unrest
    stage = Column(Integer, default=1)        # 1-N progression
    target_id = Column(Integer, nullable=True) # player_id or club_id
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    data = Column(Text, nullable=True)         # JSON payload for custom state

    club = relationship("Club", foreign_keys=[club_id])


# ── V3 Models ─────────────────────────────────────────────────────────────


class Injury(Base):
    """Detailed injury tracking with recovery curves."""
    __tablename__ = "injuries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)
    season = Column(Integer, nullable=False)
    matchday_occurred = Column(Integer, nullable=False)

    injury_type = Column(String(40), nullable=False)
    # hamstring, ankle, knee_acl, knee_mcl, groin, calf, thigh, back,
    # shoulder, concussion, foot, hip, wrist
    severity = Column(String(20), nullable=False)
    # minor, moderate, serious, career_threatening
    recovery_weeks_total = Column(Integer, nullable=False)
    recovery_weeks_remaining = Column(Integer, nullable=False)
    recovery_curve = Column(String(20), default="linear")
    # linear, exponential, setback_risk
    setback_chance = Column(Float, default=0.0)         # 0.0-0.30
    fitness_on_return = Column(Float, default=75.0)     # 70-85%
    reinjury_window_weeks = Column(Integer, default=3)  # weeks of elevated risk
    is_active = Column(Boolean, default=True)

    player = relationship("Player", foreign_keys=[player_id])
    club = relationship("Club", foreign_keys=[club_id])


class Promise(Base):
    """A promise made by the manager to a player."""
    __tablename__ = "promises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=False)
    promise_type = Column(String(40), nullable=False)
    # playing_time, new_contract, signing_player, first_team, sell_player,
    # improve_facilities, win_trophy, increase_wage
    made_matchday = Column(Integer, nullable=False)
    deadline_matchday = Column(Integer, nullable=False)
    fulfilled = Column(Boolean, default=False)
    broken = Column(Boolean, default=False)
    season = Column(Integer, nullable=False)

    player = relationship("Player", foreign_keys=[player_id])
    club = relationship("Club", foreign_keys=[club_id])


class FormHistory(Base):
    """Per-match form record for EWMA calculation."""
    __tablename__ = "form_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    season = Column(Integer, nullable=False)
    rating = Column(Float, nullable=False)           # 1-10 match rating
    minutes_played = Column(Integer, default=0)
    matchday = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("player_id", "fixture_id", name="uq_form_player_fixture"),
    )

    player = relationship("Player", foreign_keys=[player_id])
    fixture = relationship("Fixture", foreign_keys=[fixture_id])


class ConsequenceLog(Base):
    """Log of consequence chain events for debugging and display."""
    __tablename__ = "consequence_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    season = Column(Integer, nullable=False)
    matchday = Column(Integer, nullable=False)
    trigger_event = Column(String(60), nullable=False)
    # player_dropped, player_sold, promise_broken, overtraining,
    # youth_played, financial_overspend, captain_injured, match_result
    target_type = Column(String(20), nullable=False)   # player, club, board
    target_id = Column(Integer, nullable=False)
    effect = Column(Text, nullable=False)              # human-readable description
    magnitude = Column(Float, default=0.0)             # effect strength


class SaveMetadata(Base):
    """Metadata for saved games (multiple saves support)."""
    __tablename__ = "save_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    save_name = Column(String(120), nullable=False)
    club_name = Column(String(120), nullable=False)
    manager_name = Column(String(120), nullable=True)
    season = Column(Integer, nullable=False)
    matchday = Column(Integer, default=0)
    db_path = Column(String(500), nullable=False)
    created_at = Column(String(30), nullable=True)     # ISO timestamp
    last_played = Column(String(30), nullable=True)    # ISO timestamp
