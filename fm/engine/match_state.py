"""In-match player and match state representations.

These lightweight dataclasses hold the runtime state of a match in progress,
separate from the DB models so the engine stays fast and free of ORM overhead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fm.utils.helpers import clamp


@dataclass
class PlayerInMatch:
    """Runtime snapshot of a player during a match."""
    player_id: int
    name: str
    position: str
    side: str  # "home" or "away"

    # Zone assignment (updated each phase)
    zone_col: int = 3
    zone_row: int = 1

    # Key attributes (copied from DB at match start for fast access)
    overall: int = 50
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
    composure: int = 50
    reactions: int = 50
    positioning: int = 50

    # GK
    gk_diving: int = 10
    gk_handling: int = 10
    gk_kicking: int = 10
    gk_positioning: int = 10
    gk_reflexes: int = 10

    # Dynamic state
    stamina_current: float = 100.0
    fitness_mod: float = 1.0
    yellow_cards: int = 0
    red_card: bool = False
    is_gk: bool = False
    is_on_pitch: bool = True

    # ── Roles & Dynamics ──
    role: str = "CB"               # Role name from PlayerRole
    role_offset_attack: tuple[int, int] = (0, 0)
    role_offset_defend: tuple[int, int] = (0, 0)
    chemistry_partners: dict[int, float] = field(default_factory=dict) # partner_id -> strength (0-100)

    # ── Context modifiers (set before match from MatchContext) ────────
    morale_mod: float = 0.0        # -0.10 to +0.10
    form_mod: float = 0.0          # -0.08 to +0.08
    sharpness: float = 0.85        # 0.0-1.0 from training regime
    cohesion_mod: float = 0.0      # -0.05 to +0.05
    home_boost: float = 0.0        # 0.0-0.15 home advantage
    importance_mod: float = 1.0    # match importance multiplier
    weather_pass_pen: float = 0.0  # weather penalty on passing
    weather_pace_pen: float = 0.0  # weather penalty on pace
    weather_shoot_mod: float = 0.0 # weather effect on shooting
    pitch_dribble_pen: float = 0.0 # pitch condition penalty on dribbling

    # ── Player traits (set from DB at match start) ─────────────────────
    weak_foot: int = 3             # 1-5 scale (1=very weak, 5=both feet)
    consistency: int = 65          # 1-99 hidden attr — high = reliable
    big_match: int = 65            # 1-99 hidden attr — big occasion player
    injury_proneness: int = 50     # 1-99 hidden attr
    flair: int = 50                # 1-99 — creativity bonus
    temperament: int = 50          # 1-99 — red/yellow card proneness
    professionalism: int = 65      # 1-99 — consistency bonus

    # ── Match stats ────────────────────────────────────────────────────
    goals: int = 0
    assists: int = 0

    # Shooting
    shots: int = 0
    shots_on_target: int = 0
    shots_blocked: int = 0
    hit_woodwork: int = 0
    big_chances: int = 0
    big_chances_missed: int = 0

    # Passing
    passes_attempted: int = 0
    passes_completed: int = 0
    key_passes: int = 0

    # Crossing
    crosses_attempted: int = 0
    crosses_completed: int = 0

    # Dribbling
    dribbles_attempted: int = 0
    dribbles_completed: int = 0

    # Defensive
    tackles_attempted: int = 0
    tackles_won: int = 0
    interceptions_made: int = 0
    clearances: int = 0
    blocks: int = 0

    # Aerial
    aerials_won: int = 0
    aerials_lost: int = 0

    # Discipline
    fouls_committed: int = 0
    fouls_won: int = 0
    offsides_count: int = 0

    # GK
    saves: int = 0

    # Physical
    distance_covered: float = 0.0
    minutes_played: int = 0

    # Rating
    rating_points: float = 6.0
    rating_events: int = 0

    def effective(self, attr: str) -> float:
        """Get attribute modified by ALL context factors.

        Factors: stamina/fatigue (non-linear), morale, form, sharpness,
        cohesion, home advantage, weather/pitch conditions.
        """
        base = getattr(self, attr, 50)

        # --- Fatigue (non-linear, harsh below 40%) ---
        stamina_pct = self.stamina_current / 100.0
        if stamina_pct >= 0.7:
            fatigue_factor = 1.0
        elif stamina_pct >= 0.4:
            fatigue_factor = 0.7 + (stamina_pct - 0.4) * 1.0  # 0.7-1.0
        else:
            fatigue_factor = 0.3 + stamina_pct * 1.0  # 0.3-0.7

        # --- Morale: composure/finishing/positioning more affected ---
        morale_sensitive = attr in (
            "composure", "finishing", "penalties", "positioning", "vision", "passing",
        )
        morale_factor = 1.0 + self.morale_mod * (2.0 if morale_sensitive else 1.0)

        # --- Form: shooting/dribbling/passing more affected ---
        form_sensitive = attr in (
            "finishing", "shooting", "dribbling", "ball_control", "crossing", "long_shots",
        )
        form_factor = 1.0 + self.form_mod * (1.5 if form_sensitive else 0.8)

        # --- Sharpness (from training regime) ---
        sharpness_factor = 0.85 + self.sharpness * 0.15  # 0.85-1.0

        # --- Cohesion: passing and positioning more affected ---
        cohesion_sensitive = attr in (
            "short_passing", "long_passing", "passing", "vision",
            "positioning", "interceptions",
        )
        cohesion_factor = 1.0 + self.cohesion_mod * (2.0 if cohesion_sensitive else 0.5)

        # --- Home boost: mental attributes benefit most ---
        mental_attrs = ("composure", "aggression", "reactions", "positioning")
        home_factor = 1.0 + (
            self.home_boost if attr in mental_attrs else self.home_boost * 0.3
        )

        # --- Weather / pitch penalties ---
        weather_factor = 1.0
        if attr in ("short_passing", "long_passing", "passing", "crossing", "vision"):
            weather_factor -= self.weather_pass_pen
        if attr in ("pace", "acceleration", "sprint_speed", "agility"):
            weather_factor -= self.weather_pace_pen
        if attr in ("shooting", "finishing", "long_shots", "free_kick_accuracy"):
            weather_factor += self.weather_shoot_mod
        if attr in ("dribbling", "ball_control", "balance", "agility"):
            weather_factor -= self.pitch_dribble_pen

        # --- Consistency: random variance reduced for consistent players ---
        # Low consistency (1-40): can have bad days (-5% to +2%)
        # High consistency (80-99): very reliable (-1% to +1%)
        import random as _rng
        consistency_range = max(0.01, (100 - self.consistency) / 100.0 * 0.08)
        consistency_factor = 1.0 + _rng.uniform(-consistency_range, consistency_range * 0.4)

        # --- Big match factor: affects composure, finishing in high-importance games ---
        big_match_factor = 1.0
        if self.importance_mod > 1.05:  # big match
            big_match_bonus = (self.big_match - 50) / 500.0  # -0.10 to +0.10
            if attr in ("composure", "finishing", "penalties", "positioning"):
                big_match_factor = 1.0 + big_match_bonus * 2.0
            else:
                big_match_factor = 1.0 + big_match_bonus

        # --- Combine ---
        result = (
            base * fatigue_factor * morale_factor * form_factor
            * sharpness_factor * cohesion_factor * home_factor
            * weather_factor * self.fitness_mod * consistency_factor
            * big_match_factor
        )
        return max(result, 1.0)

    def apply_context(self, **kwargs) -> None:
        """Apply match context modifiers from MatchContext."""
        for key, val in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, val)

    @property
    def avg_rating(self) -> float:
        if self.rating_events == 0:
            return 6.0
        return self.rating_points / self.rating_events

    @property
    def pass_accuracy(self) -> float:
        if self.passes_attempted == 0:
            return 0.0
        return (self.passes_completed / self.passes_attempted) * 100.0

    @property
    def tackle_success(self) -> float:
        if self.tackles_attempted == 0:
            return 0.0
        return (self.tackles_won / self.tackles_attempted) * 100.0

    @property
    def dribble_success(self) -> float:
        if self.dribbles_attempted == 0:
            return 0.0
        return (self.dribbles_completed / self.dribbles_attempted) * 100.0

    @classmethod
    def from_db_player(cls, p, side: str) -> PlayerInMatch:
        """Build from a Player ORM object."""
        is_gk = p.position == "GK"
        return cls(
            player_id=p.id,
            name=p.short_name or p.name,
            position=p.position,
            side=side,
            overall=p.overall or 50,
            pace=p.pace, acceleration=p.acceleration, sprint_speed=p.sprint_speed,
            shooting=p.shooting, finishing=p.finishing, shot_power=p.shot_power,
            long_shots=p.long_shots, volleys=p.volleys, penalties=p.penalties,
            passing=p.passing, vision=p.vision, crossing=p.crossing,
            free_kick_accuracy=p.free_kick_accuracy,
            short_passing=p.short_passing, long_passing=p.long_passing,
            curve=p.curve, dribbling=p.dribbling, agility=p.agility,
            balance=p.balance, ball_control=p.ball_control,
            defending=p.defending, marking=p.marking,
            standing_tackle=p.standing_tackle, sliding_tackle=p.sliding_tackle,
            interceptions=p.interceptions, heading_accuracy=p.heading_accuracy,
            physical=p.physical, stamina=p.stamina, strength=p.strength,
            jumping=p.jumping, aggression=p.aggression,
            composure=p.composure, reactions=p.reactions, positioning=p.positioning,
            gk_diving=p.gk_diving, gk_handling=p.gk_handling,
            gk_kicking=p.gk_kicking, gk_positioning=p.gk_positioning,
            gk_reflexes=p.gk_reflexes,
            stamina_current=p.fitness if p.fitness else 100.0,
            fitness_mod=min(p.fitness / 100.0, 1.0) if p.fitness else 1.0,
            is_gk=is_gk,
            # Traits from DB (with safe defaults)
            weak_foot=getattr(p, 'weak_foot', 3) or 3,
            consistency=getattr(p, 'consistency', 65) or 65,
            big_match=getattr(p, 'big_match', 65) or 65,
            injury_proneness=getattr(p, 'injury_proneness', 50) or 50,
            flair=getattr(p, 'flair', 50) or 50,
            temperament=getattr(p, 'temperament', 50) or 50,
            professionalism=getattr(p, 'professionalism', 65) or 65,
        )


@dataclass
class Scorecard:
    """10-minute interval summary."""
    minute: int
    home_goals: int
    away_goals: int
    home_possession: float
    away_possession: float
    home_shots: int
    away_shots: int
    home_sot: int
    away_sot: int
    home_xg: float
    away_xg: float
    home_passes: int = 0
    away_passes: int = 0
    home_fouls: int = 0
    away_fouls: int = 0
    home_corners: int = 0
    away_corners: int = 0
    events_text: list[str] = field(default_factory=list)
    zone_heatmap_home: str = ""
    zone_heatmap_away: str = ""


@dataclass
class TeamStats:
    """Aggregated team statistics for a match."""
    goals: int = 0
    shots: int = 0
    shots_on_target: int = 0
    shots_blocked: int = 0
    woodwork: int = 0
    big_chances: int = 0
    big_chances_missed: int = 0
    xg: float = 0.0
    possession: float = 50.0
    passes: int = 0
    passes_completed: int = 0
    pass_accuracy: float = 0.0
    key_passes: int = 0
    crosses: int = 0
    crosses_completed: int = 0
    dribbles: int = 0
    dribbles_completed: int = 0
    tackles: int = 0
    tackles_won: int = 0
    interceptions: int = 0
    clearances: int = 0
    blocks: int = 0
    aerials_won: int = 0
    aerials_lost: int = 0
    corners: int = 0
    fouls: int = 0
    offsides: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    saves: int = 0


@dataclass
class MatchResult:
    """Final output of a match simulation."""
    home_goals: int = 0
    away_goals: int = 0
    home_possession: float = 50.0
    home_xg: float = 0.0
    away_xg: float = 0.0
    home_stats: TeamStats = field(default_factory=TeamStats)
    away_stats: TeamStats = field(default_factory=TeamStats)
    scorecards: list[Scorecard] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    commentary: list[str] = field(default_factory=list)
    home_lineup: list[PlayerInMatch] = field(default_factory=list)
    away_lineup: list[PlayerInMatch] = field(default_factory=list)
    motm: PlayerInMatch | None = None  # Man of the match


@dataclass
class MatchState:
    """Mutable state of a match in progress."""
    home_players: list[PlayerInMatch] = field(default_factory=list)
    away_players: list[PlayerInMatch] = field(default_factory=list)
    home_subs: list[PlayerInMatch] = field(default_factory=list)
    away_subs: list[PlayerInMatch] = field(default_factory=list)

    # Current ball state
    ball_side: str = "home"
    ball_zone_col: int = 3
    ball_zone_row: int = 1
    ball_carrier: PlayerInMatch | None = None

    # Scores
    home_goals: int = 0
    away_goals: int = 0

    # Possession
    home_possession_ticks: int = 0
    away_possession_ticks: int = 0

    # ── Team stats accumulators ────────────────────────────────────────
    # Shots
    home_shots: int = 0
    away_shots: int = 0
    home_sot: int = 0
    away_sot: int = 0
    home_shots_blocked: int = 0
    away_shots_blocked: int = 0
    home_woodwork: int = 0
    away_woodwork: int = 0
    home_big_chances: int = 0
    away_big_chances: int = 0
    home_big_chances_missed: int = 0
    away_big_chances_missed: int = 0
    home_xg: float = 0.0
    away_xg: float = 0.0

    # Passing
    home_passes: int = 0
    away_passes: int = 0
    home_passes_completed: int = 0
    away_passes_completed: int = 0
    home_key_passes: int = 0
    away_key_passes: int = 0

    # Crossing
    home_crosses: int = 0
    away_crosses: int = 0
    home_crosses_completed: int = 0
    away_crosses_completed: int = 0

    # Dribbling
    home_dribbles: int = 0
    away_dribbles: int = 0
    home_dribbles_completed: int = 0
    away_dribbles_completed: int = 0

    # Defensive
    home_tackles: int = 0
    away_tackles: int = 0
    home_tackles_won: int = 0
    away_tackles_won: int = 0
    home_interceptions: int = 0
    away_interceptions: int = 0
    home_clearances: int = 0
    away_clearances: int = 0
    home_blocks: int = 0
    away_blocks: int = 0

    # Aerial
    home_aerials_won: int = 0
    away_aerials_won: int = 0
    home_aerials_lost: int = 0
    away_aerials_lost: int = 0

    # Set pieces
    home_corners: int = 0
    away_corners: int = 0
    home_fouls: int = 0
    away_fouls: int = 0
    home_offsides: int = 0
    away_offsides: int = 0
    home_yellow_cards: int = 0
    away_yellow_cards: int = 0
    home_red_cards: int = 0
    away_red_cards: int = 0

    # GK
    home_saves: int = 0
    away_saves: int = 0

    # Momentum (-1.0 to 1.0)
    home_momentum: float = 0.0
    away_momentum: float = 0.0

    # Substitution tracking
    home_subs_made: int = 0
    away_subs_made: int = 0
    max_subs: int = 5

    # Commentary and events
    events: list[dict] = field(default_factory=list)
    commentary: list[str] = field(default_factory=list)
    scorecards: list[Scorecard] = field(default_factory=list)
    current_minute: int = 0

    @property
    def home_possession_pct(self) -> float:
        total = self.home_possession_ticks + self.away_possession_ticks
        if total == 0:
            return 50.0
        return (self.home_possession_ticks / total) * 100.0

    @property
    def home_pass_accuracy(self) -> float:
        if self.home_passes == 0:
            return 0.0
        return (self.home_passes_completed / self.home_passes) * 100.0

    @property
    def away_pass_accuracy(self) -> float:
        if self.away_passes == 0:
            return 0.0
        return (self.away_passes_completed / self.away_passes) * 100.0

    def get_attacking_players(self) -> list[PlayerInMatch]:
        plist = self.home_players if self.ball_side == "home" else self.away_players
        return [p for p in plist if p.is_on_pitch and not p.red_card]

    def get_defending_players(self) -> list[PlayerInMatch]:
        plist = self.away_players if self.ball_side == "home" else self.home_players
        return [p for p in plist if p.is_on_pitch and not p.red_card]

    def get_gk(self, side: str) -> PlayerInMatch | None:
        plist = self.home_players if side == "home" else self.away_players
        for p in plist:
            if p.is_gk and p.is_on_pitch:
                return p
        return None

    def _inc(self, side: str, stat: str, amount: int | float = 1):
        """Increment a team stat by side."""
        attr = f"{'home' if side == 'home' else 'away'}_{stat}"
        setattr(self, attr, getattr(self, attr, 0) + amount)

    def _update_momentum(self, side: str, event: str):
        """Adjust momentum for *side* based on the match event.

        Momentum is a float in [-1.0, 1.0].  Positive events push it towards
        1.0, negative events towards -1.0.  Natural decay pulls it back to 0.
        """
        # Deltas for each event type
        _MOMENTUM_DELTAS = {
            "goal":              0.25,
            "shot_on_target":    0.08,
            "dribble_completed": 0.04,
            "tackle_won":        0.06,
            "save":              0.07,
            "concede":          -0.25,
            "turnover":         -0.05,
            "yellow_card":      -0.08,
            "red_card":         -0.20,
            "corner_won":        0.03,
            "free_kick_won":     0.04,
        }
        delta = _MOMENTUM_DELTAS.get(event, 0.0)

        if side == "home":
            self.home_momentum = clamp(self.home_momentum + delta, -1.0, 1.0)
            # Mirror effect on opponent
            self.away_momentum = clamp(self.away_momentum - delta * 0.3, -1.0, 1.0)
        else:
            self.away_momentum = clamp(self.away_momentum + delta, -1.0, 1.0)
            self.home_momentum = clamp(self.home_momentum - delta * 0.3, -1.0, 1.0)

    def _decay_momentum(self, rate: float = 0.02):
        """Gradually pull momentum back towards zero (called each minute)."""
        if self.home_momentum > 0:
            self.home_momentum = max(0.0, self.home_momentum - rate)
        elif self.home_momentum < 0:
            self.home_momentum = min(0.0, self.home_momentum + rate)
        if self.away_momentum > 0:
            self.away_momentum = max(0.0, self.away_momentum - rate)
        elif self.away_momentum < 0:
            self.away_momentum = min(0.0, self.away_momentum + rate)

    def get_momentum(self, side: str) -> float:
        """Return the current momentum for *side*."""
        return self.home_momentum if side == "home" else self.away_momentum

    def _build_team_stats(self, side: str) -> TeamStats:
        """Build a TeamStats snapshot for one side."""
        s = "home" if side == "home" else "away"
        poss = self.home_possession_pct if s == "home" else 100.0 - self.home_possession_pct
        pa = getattr(self, f"{s}_passes")
        pc = getattr(self, f"{s}_passes_completed")
        return TeamStats(
            goals=getattr(self, f"{s}_goals"),
            shots=getattr(self, f"{s}_shots"),
            shots_on_target=getattr(self, f"{s}_sot"),
            shots_blocked=getattr(self, f"{s}_shots_blocked"),
            woodwork=getattr(self, f"{s}_woodwork"),
            big_chances=getattr(self, f"{s}_big_chances"),
            big_chances_missed=getattr(self, f"{s}_big_chances_missed"),
            xg=getattr(self, f"{s}_xg"),
            possession=round(poss, 1),
            passes=pa, passes_completed=pc,
            pass_accuracy=round((pc / pa * 100) if pa else 0, 1),
            key_passes=getattr(self, f"{s}_key_passes"),
            crosses=getattr(self, f"{s}_crosses"),
            crosses_completed=getattr(self, f"{s}_crosses_completed"),
            dribbles=getattr(self, f"{s}_dribbles"),
            dribbles_completed=getattr(self, f"{s}_dribbles_completed"),
            tackles=getattr(self, f"{s}_tackles"),
            tackles_won=getattr(self, f"{s}_tackles_won"),
            interceptions=getattr(self, f"{s}_interceptions"),
            clearances=getattr(self, f"{s}_clearances"),
            blocks=getattr(self, f"{s}_blocks"),
            aerials_won=getattr(self, f"{s}_aerials_won"),
            aerials_lost=getattr(self, f"{s}_aerials_lost"),
            corners=getattr(self, f"{s}_corners"),
            fouls=getattr(self, f"{s}_fouls"),
            offsides=getattr(self, f"{s}_offsides"),
            yellow_cards=getattr(self, f"{s}_yellow_cards"),
            red_cards=getattr(self, f"{s}_red_cards"),
            saves=getattr(self, f"{s}_saves"),
        )

    def to_result(self) -> MatchResult:
        all_players = [p for p in self.home_players + self.away_players if p.is_on_pitch or p.goals > 0]
        motm = max(all_players, key=lambda p: p.avg_rating) if all_players else None

        # Cap extreme scorelines (real football rarely exceeds 6 goals for one team)
        home_g = min(self.home_goals, 6)
        away_g = min(self.away_goals, 6)

        return MatchResult(
            home_goals=home_g,
            away_goals=away_g,
            home_possession=self.home_possession_pct,
            home_xg=self.home_xg,
            away_xg=self.away_xg,
            home_stats=self._build_team_stats("home"),
            away_stats=self._build_team_stats("away"),
            scorecards=self.scorecards,
            events=self.events,
            commentary=self.commentary,
            home_lineup=self.home_players,
            away_lineup=self.away_players,
            motm=motm,
        )
