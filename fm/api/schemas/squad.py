"""Pydantic schemas for squad and player endpoints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PlayerDetail(BaseModel):
    """Full player representation with all attributes and season stats."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str | None = None
    age: int
    nationality: str | None = None
    position: str
    secondary_positions: str | None = None
    club_id: int | None = None
    contract_expiry: int | None = None
    wage: float = 0.0
    market_value: float = 0.0

    overall: int
    potential: int

    # Technical
    pace: int = 50
    acceleration: int = 50
    sprint_speed: int = 50
    shooting: int = 50
    finishing: int = 50
    shot_power: int = 50
    long_shots: int = 50
    volleys: int = 50
    penalties: int = 50
    passing: int = 50
    vision: int = 50
    crossing: int = 50
    free_kick_accuracy: int = 50
    short_passing: int = 50
    long_passing: int = 50
    curve: int = 50
    dribbling: int = 50
    agility: int = 50
    balance: int = 50
    ball_control: int = 50
    defending: int = 50
    marking: int = 50
    standing_tackle: int = 50
    sliding_tackle: int = 50
    interceptions: int = 50
    heading_accuracy: int = 50
    physical: int = 50
    stamina: int = 50
    strength: int = 50
    jumping: int = 50
    aggression: int = 50

    # Mental
    composure: int = 50
    reactions: int = 50
    positioning: int = 50
    att_work_rate: str = "medium"
    def_work_rate: str = "medium"

    # GK
    gk_diving: int = 10
    gk_handling: int = 10
    gk_kicking: int = 10
    gk_positioning: int = 10
    gk_reflexes: int = 10

    # Personality
    leadership: int = 50
    teamwork: int = 50
    determination: int = 50

    # Physical profile
    height_cm: int = 180
    weight_kg: int = 75
    preferred_foot: str = "right"
    weak_foot_ability: int = 2
    traits: str | None = None

    # Dynamic state
    fitness: float = 100.0
    morale: float = 65.0
    form: float = 65.0
    injured_weeks: int = 0
    suspended_matches: int = 0
    squad_role: str = "not_set"

    # Season accumulators
    goals_season: int = 0
    assists_season: int = 0
    minutes_season: int = 0
    yellow_cards_season: int = 0
    red_cards_season: int = 0


class PlayerComparison(BaseModel):
    """Side-by-side comparison of two players."""
    player_a: PlayerDetail
    player_b: PlayerDetail


class SquadPlayer(BaseModel):
    """Player in a squad listing with role context."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    position: str
    overall: int
    age: int
    fitness: float
    morale: float
    form: float
    injured_weeks: int
    suspended_matches: int
    squad_role: str
    goals_season: int
    assists_season: int
    wage: float
    market_value: float


class SquadList(BaseModel):
    """Full squad with summary stats."""
    players: list[SquadPlayer]
    total_players: int
    average_overall: float
    average_age: float
    total_wages: float
