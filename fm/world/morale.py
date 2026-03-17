"""Team talks, morale management, team spirit, and player relationships.

Handles pre-match / post-match team talks, morale updates based on
results, team spirit tracking, manager-player relationships, individual
player conversations, and automatic morale triggers from game events.
"""
from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from fm.db.models import Club, Player, LeagueStanding, PlayerStats, NewsItem


# ── Enums ──────────────────────────────────────────────────────────────────


class TeamTalkType(str, enum.Enum):
    MOTIVATE = "motivate"           # Fire up the team
    CALM = "calm"                   # Reduce pressure
    PRAISE = "praise"               # After good result
    CRITICIZE = "criticize"         # After bad result
    FOCUS = "focus"                 # Maintain concentration
    NO_PRESSURE = "no_pressure"     # Remove expectations
    DEMAND_MORE = "demand_more"     # Aggressive push for improvement
    SHOW_FAITH = "show_faith"       # Express confidence in the squad
    PASSIONATE = "passionate"       # Emotional speech
    ANALYTICAL = "analytical"       # Tactical review, facts-based


class TeamSpiritLevel(str, enum.Enum):
    SUPERB = "superb"       # 85-100
    GOOD = "good"           # 70-85
    DECENT = "decent"       # 55-70
    POOR = "poor"           # 40-55
    VERY_POOR = "very_poor" # 25-40
    ABYSMAL = "abysmal"     # 0-25


class PromiseType(str, enum.Enum):
    PLAYING_TIME = "playing_time"       # Promise more minutes
    TRANSFER_LIST = "transfer_list"     # Promise to list for transfer
    NEW_CONTRACT = "new_contract"       # Promise improved terms
    SIGNING = "signing"                 # Promise a new signing in their position
    CAPTAIN = "captain"                 # Promise captaincy


class IndividualTalkTopic(str, enum.Enum):
    PLAYING_TIME = "playing_time"
    FORM = "form"
    CONTRACT = "contract"
    BEHAVIOR = "behavior"
    PRAISE_PERFORMANCE = "praise_performance"
    ENCOURAGE = "encourage"
    WARN_BEHAVIOR = "warn_behavior"


class IndividualTalkTone(str, enum.Enum):
    SUPPORTIVE = "supportive"
    NEUTRAL = "neutral"
    FIRM = "firm"
    AGGRESSIVE = "aggressive"


# ── Data classes ───────────────────────────────────────────────────────────


@dataclass
class PromiseRecord:
    """A promise made by the manager to a player."""
    player_id: int
    promise_type: PromiseType
    details: str
    matchday_made: int
    season_made: int
    deadline_matchday: int      # when it must be fulfilled by
    fulfilled: bool = False
    broken: bool = False


@dataclass
class TalkOutcome:
    """Result of an individual or team talk."""
    player_name: str
    morale_delta: float
    description: str
    relationship_delta: float = 0.0


# ── Team Spirit Manager ───────────────────────────────────────────────────


class TeamSpiritManager:
    """Tracks and calculates collective team mood, separate from individual morale."""

    def __init__(self, session: Session):
        self.session = session
        # In-memory spirit cache: club_id -> float (0-100)
        self._spirit_cache: dict[int, float] = {}

    def calculate_team_spirit(self, club_id: int) -> float:
        """Calculate team spirit from multiple factors.

        Factors: average morale, recent results streak, captain influence,
        squad harmony (wage disparity), and squad depth satisfaction.
        Returns a value 0-100.
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return 50.0

        # Factor 1: Average morale (weight: 40%)
        avg_morale = sum(p.morale or 65.0 for p in players) / len(players)

        # Factor 2: Recent form streak (weight: 25%)
        form_score = self._form_spirit_component(club_id)

        # Factor 3: Squad harmony - wage disparity (weight: 15%)
        harmony_score = self._squad_harmony_component(players)

        # Factor 4: Captain influence (weight: 10%)
        captain_score = self._captain_influence_component(players)

        # Factor 5: Squad depth satisfaction (weight: 10%)
        depth_score = self._depth_satisfaction_component(players)

        spirit = (
            avg_morale * 0.40
            + form_score * 0.25
            + harmony_score * 0.15
            + captain_score * 0.10
            + depth_score * 0.10
        )
        spirit = max(0.0, min(100.0, spirit))
        self._spirit_cache[club_id] = spirit
        return spirit

    def get_spirit_level(self, club_id: int) -> TeamSpiritLevel:
        """Return the categorical spirit level for a club."""
        spirit = self._spirit_cache.get(club_id)
        if spirit is None:
            spirit = self.calculate_team_spirit(club_id)
        if spirit >= 85:
            return TeamSpiritLevel.SUPERB
        elif spirit >= 70:
            return TeamSpiritLevel.GOOD
        elif spirit >= 55:
            return TeamSpiritLevel.DECENT
        elif spirit >= 40:
            return TeamSpiritLevel.POOR
        elif spirit >= 25:
            return TeamSpiritLevel.VERY_POOR
        return TeamSpiritLevel.ABYSMAL

    def get_spirit_effects(self, club_id: int) -> dict:
        """Return performance modifiers based on current team spirit.

        Effects dict keys: passing_mod, positioning_mod, error_rate,
        red_card_risk, description.
        """
        level = self.get_spirit_level(club_id)
        effects = {
            TeamSpiritLevel.SUPERB: {
                "passing_mod": 0.05,
                "positioning_mod": 0.05,
                "error_rate": -0.03,
                "red_card_risk": 0.0,
                "description": "The squad is united and full of belief.",
            },
            TeamSpiritLevel.GOOD: {
                "passing_mod": 0.02,
                "positioning_mod": 0.02,
                "error_rate": -0.01,
                "red_card_risk": 0.0,
                "description": "Good atmosphere in the dressing room.",
            },
            TeamSpiritLevel.DECENT: {
                "passing_mod": 0.0,
                "positioning_mod": 0.0,
                "error_rate": 0.0,
                "red_card_risk": 0.0,
                "description": "The squad mood is steady.",
            },
            TeamSpiritLevel.POOR: {
                "passing_mod": -0.03,
                "positioning_mod": -0.03,
                "error_rate": 0.02,
                "red_card_risk": 0.01,
                "description": "Tension is building within the squad.",
            },
            TeamSpiritLevel.VERY_POOR: {
                "passing_mod": -0.06,
                "positioning_mod": -0.06,
                "error_rate": 0.05,
                "red_card_risk": 0.03,
                "description": "Arguments on the pitch are becoming common.",
            },
            TeamSpiritLevel.ABYSMAL: {
                "passing_mod": -0.10,
                "positioning_mod": -0.10,
                "error_rate": 0.08,
                "red_card_risk": 0.06,
                "description": "The dressing room is toxic. Players are at each other's throats.",
            },
        }
        return effects.get(level, effects[TeamSpiritLevel.DECENT])

    # ── Internal components ────────────────────────────────────────────────

    def _form_spirit_component(self, club_id: int) -> float:
        """Score 0-100 based on recent results form string."""
        standing = (
            self.session.query(LeagueStanding)
            .filter_by(club_id=club_id)
            .order_by(LeagueStanding.season.desc())
            .first()
        )
        if not standing or not standing.form:
            return 55.0  # neutral

        form_str = standing.form[-5:]  # last 5 results
        score = 55.0
        for ch in form_str:
            if ch == "W":
                score += 9.0
            elif ch == "D":
                score += 2.0
            elif ch == "L":
                score -= 7.0
        return max(0.0, min(100.0, score))

    def _squad_harmony_component(self, players: list[Player]) -> float:
        """Score 0-100 based on wage equality. Large disparities hurt spirit."""
        wages = [p.wage or 0 for p in players if (p.wage or 0) > 0]
        if len(wages) < 2:
            return 65.0

        avg_wage = sum(wages) / len(wages)
        if avg_wage == 0:
            return 65.0

        # Coefficient of variation: std / mean
        variance = sum((w - avg_wage) ** 2 for w in wages) / len(wages)
        std = variance ** 0.5
        cv = std / avg_wage

        # CV of 0 = perfect harmony (100), CV of 2+ = terrible (20)
        harmony = max(20.0, 100.0 - cv * 40.0)
        return harmony

    def _captain_influence_component(self, players: list[Player]) -> float:
        """Score 0-100 based on the best leader in the squad.

        Uses composure + big_match as a proxy for leadership quality.
        """
        if not players:
            return 50.0

        # Find the best "captain" candidate
        best_leadership = 0
        for p in players:
            leadership = ((p.composure or 50) + (p.big_match or 50)) / 2.0
            if leadership > best_leadership:
                best_leadership = leadership

        # Scale: 80+ leadership = 90 score, 50 leadership = 50 score
        return max(20.0, min(95.0, best_leadership * 1.1))

    def _depth_satisfaction_component(self, players: list[Player]) -> float:
        """Score 0-100 based on whether squad has enough players and positions covered."""
        if len(players) < 11:
            return 15.0

        # Check position coverage
        positions_needed = {"GK", "CB", "CM", "ST"}
        positions_present = {p.position for p in players}
        coverage = len(positions_needed & positions_present) / len(positions_needed)

        # Squad size factor: 18-25 is ideal, below or above is worse
        size = len(players)
        if 18 <= size <= 28:
            size_factor = 1.0
        elif size < 18:
            size_factor = size / 18.0
        else:
            size_factor = max(0.6, 1.0 - (size - 28) * 0.05)

        return min(100.0, (coverage * 50 + 50) * size_factor)


# ── Manager-Player Relationship ───────────────────────────────────────────


class ManagerRelationship:
    """Tracks how each player feels about the manager.

    Relationship score: 0 (hostile) to 100 (devoted).
    Affected by promises kept/broken, playing time, talks, and results.
    """

    def __init__(self, session: Session):
        self.session = session
        # In-memory: player_id -> relationship score (0-100)
        self._relationships: dict[int, float] = {}
        # In-memory promise tracking: player_id -> list of PromiseRecord
        self._promises: dict[int, list[PromiseRecord]] = {}

    def get_relationship(self, player_id: int) -> float:
        """Get current relationship score for a player. Default is 60."""
        return self._relationships.get(player_id, 60.0)

    def set_relationship(self, player_id: int, value: float) -> None:
        """Set a player's relationship score, clamped 0-100."""
        self._relationships[player_id] = max(0.0, min(100.0, value))

    def adjust_relationship(self, player_id: int, delta: float) -> float:
        """Adjust relationship by delta and return the new value."""
        current = self.get_relationship(player_id)
        new_val = max(0.0, min(100.0, current + delta))
        self._relationships[player_id] = new_val
        return new_val

    def process_promise(
        self,
        player_id: int,
        promise_type: PromiseType,
        details: str,
        current_matchday: int,
        current_season: int,
        deadline_weeks: int = 12,
    ) -> str:
        """Record a promise made to a player.

        Returns a description of the player's reaction.
        """
        record = PromiseRecord(
            player_id=player_id,
            promise_type=promise_type,
            details=details,
            matchday_made=current_matchday,
            season_made=current_season,
            deadline_matchday=current_matchday + deadline_weeks,
        )
        if player_id not in self._promises:
            self._promises[player_id] = []

        # Check if there's already an active promise of the same type
        existing = [
            p for p in self._promises[player_id]
            if p.promise_type == promise_type and not p.fulfilled and not p.broken
        ]
        if existing:
            return "The player reminds you that you already made this promise."

        self._promises[player_id].append(record)

        # Small relationship boost for making the promise
        self.adjust_relationship(player_id, 3.0)

        player = self.session.get(Player, player_id)
        name = player.short_name or player.name if player else "The player"
        reactions = {
            PromiseType.PLAYING_TIME: f"{name} is pleased to hear they'll get more game time.",
            PromiseType.TRANSFER_LIST: f"{name} accepts your decision and hopes for a good move.",
            PromiseType.NEW_CONTRACT: f"{name} looks forward to discussing improved terms.",
            PromiseType.SIGNING: f"{name} is relieved to hear reinforcements are coming.",
            PromiseType.CAPTAIN: f"{name} is honoured by the prospect of wearing the armband.",
        }
        return reactions.get(promise_type, f"{name} acknowledges the promise.")

    def check_promises(self, club_id: int, current_matchday: int, current_season: int) -> list[str]:
        """Check all promises for a club. Broken promises damage relationships.

        Returns list of news/event descriptions.
        """
        events: list[str] = []
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        player_ids = {p.id for p in players}

        for pid in list(self._promises.keys()):
            if pid not in player_ids:
                continue

            for promise in self._promises.get(pid, []):
                if promise.fulfilled or promise.broken:
                    continue

                # Check if deadline has passed
                if current_matchday < promise.deadline_matchday:
                    continue

                # Check if promise was fulfilled
                fulfilled = self._check_promise_fulfilled(pid, promise)

                player = self.session.get(Player, pid)
                name = player.short_name or player.name if player else "A player"

                if fulfilled:
                    promise.fulfilled = True
                    self.adjust_relationship(pid, 8.0)
                    events.append(f"{name} is happy that you kept your promise ({promise.promise_type.value}).")
                else:
                    promise.broken = True
                    penalty = -15.0
                    self.adjust_relationship(pid, penalty)
                    # Broken promises also hurt morale
                    if player:
                        player.morale = max(0.0, (player.morale or 65.0) - 10.0)
                    events.append(
                        f"{name} is furious! You broke your promise about "
                        f"{promise.promise_type.value}. Trust has been severely damaged."
                    )

        return events

    def _check_promise_fulfilled(self, player_id: int, promise: PromiseRecord) -> bool:
        """Check if a specific promise has been fulfilled."""
        player = self.session.get(Player, player_id)
        if not player:
            return False

        if promise.promise_type == PromiseType.PLAYING_TIME:
            # Check if player has reasonable appearances since promise
            stats = (
                self.session.query(PlayerStats)
                .filter_by(player_id=player_id, season=promise.season_made)
                .first()
            )
            if stats and (stats.appearances or 0) >= 5:
                return True
            return False

        elif promise.promise_type == PromiseType.NEW_CONTRACT:
            # Check if contract was extended (higher expiry year)
            return (player.contract_expiry or 0) > promise.season_made + 1

        elif promise.promise_type == PromiseType.TRANSFER_LIST:
            # Player moved to a different club
            return player.club_id is None or player.club_id != promise.player_id

        # Default: assume not fulfilled
        return False

    def process_match_played(self, club_id: int, lineup_ids: set[int]) -> None:
        """Adjust relationships based on who played and who didn't.

        Starters who expected playing time get a small boost.
        Players who haven't played in a while get frustrated.
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()

        for p in players:
            if (p.injured_weeks or 0) > 0 or (p.suspended_matches or 0) > 0:
                continue  # injured/suspended players don't complain

            if p.id in lineup_ids:
                # Small boost for getting game time
                self.adjust_relationship(p.id, 1.0)
            else:
                # Higher overall players expect to play
                if (p.overall or 50) >= 75:
                    self.adjust_relationship(p.id, -2.0)
                elif (p.overall or 50) >= 65:
                    self.adjust_relationship(p.id, -0.5)

    def get_unhappy_players(self, club_id: int) -> list[tuple[int, str, float]]:
        """Return list of (player_id, player_name, relationship) for unhappy players."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        unhappy = []
        for p in players:
            rel = self.get_relationship(p.id)
            if rel < 40.0:
                unhappy.append((p.id, p.short_name or p.name, rel))
        unhappy.sort(key=lambda x: x[2])
        return unhappy


# ── Individual Talk Manager ───────────────────────────────────────────────


class IndividualTalkManager:
    """Handle one-on-one conversations between the manager and a player."""

    def __init__(self, session: Session, relationship_mgr: ManagerRelationship):
        self.session = session
        self.rel_mgr = relationship_mgr

    def talk_to_player(
        self,
        player_id: int,
        topic: IndividualTalkTopic,
        tone: IndividualTalkTone = IndividualTalkTone.NEUTRAL,
    ) -> TalkOutcome:
        """Have a one-on-one conversation with a player.

        The outcome depends on topic, tone, the player's personality
        (composure, aggression), and the current relationship.
        """
        player = self.session.get(Player, player_id)
        if not player:
            return TalkOutcome("Unknown", 0.0, "Player not found.")

        name = player.short_name or player.name
        composure = (player.composure or 50) / 100.0
        aggression = (player.aggression or 50) / 100.0
        current_rel = self.rel_mgr.get_relationship(player_id)
        current_morale = player.morale or 65.0

        morale_delta, rel_delta, description = self._resolve_talk(
            topic, tone, composure, aggression, current_rel, current_morale, name
        )

        # Apply changes
        player.morale = max(0.0, min(100.0, current_morale + morale_delta))
        self.rel_mgr.adjust_relationship(player_id, rel_delta)
        self.session.flush()

        return TalkOutcome(
            player_name=name,
            morale_delta=morale_delta,
            description=description,
            relationship_delta=rel_delta,
        )

    def _resolve_talk(
        self,
        topic: IndividualTalkTopic,
        tone: IndividualTalkTone,
        composure: float,
        aggression: float,
        relationship: float,
        morale: float,
        name: str,
    ) -> tuple[float, float, str]:
        """Resolve the outcome of a player conversation.

        Returns (morale_delta, relationship_delta, description).
        """
        # Tone modifiers: how well the tone lands
        tone_mod = {
            IndividualTalkTone.SUPPORTIVE: 1.2 if relationship > 40 else 0.8,
            IndividualTalkTone.NEUTRAL: 1.0,
            IndividualTalkTone.FIRM: 1.1 if composure > 0.5 else 0.7,
            IndividualTalkTone.AGGRESSIVE: 1.3 if aggression > 0.6 else 0.5,
        }[tone]

        # --- Playing time ---
        if topic == IndividualTalkTopic.PLAYING_TIME:
            if morale < 50:
                morale_d = 4.0 * tone_mod + random.uniform(-1, 2)
                rel_d = 3.0
                desc = f"{name} appreciates you addressing their concerns about game time."
            else:
                morale_d = random.uniform(-1, 2)
                rel_d = 1.0
                desc = f"{name} acknowledges the conversation about playing time."

        # --- Form ---
        elif topic == IndividualTalkTopic.FORM:
            if morale < 45:
                morale_d = 5.0 * tone_mod + random.uniform(0, 2)
                rel_d = 2.0
                desc = f"{name} seems motivated after discussing their form."
            else:
                morale_d = 2.0 * tone_mod + random.uniform(-1, 1)
                rel_d = 1.0
                desc = f"{name} takes the feedback on board."

        # --- Contract ---
        elif topic == IndividualTalkTopic.CONTRACT:
            morale_d = random.uniform(0, 3)
            rel_d = 2.0
            desc = f"{name} is glad you're thinking about their future at the club."

        # --- Behavior warning ---
        elif topic == IndividualTalkTopic.BEHAVIOR:
            if aggression > 0.6 and tone == IndividualTalkTone.AGGRESSIVE:
                morale_d = -5.0 + random.uniform(-3, 0)
                rel_d = -6.0
                desc = f"{name} reacts badly to the confrontation and storms out!"
            elif composure > 0.5:
                morale_d = -1.0 + random.uniform(-1, 1)
                rel_d = -2.0
                desc = f"{name} accepts the warning calmly but is visibly displeased."
            else:
                morale_d = -3.0 + random.uniform(-2, 1)
                rel_d = -4.0
                desc = f"{name} is upset by the talk but agrees to improve."

        # --- Praise performance ---
        elif topic == IndividualTalkTopic.PRAISE_PERFORMANCE:
            morale_d = 5.0 * tone_mod + random.uniform(1, 3)
            rel_d = 5.0
            desc = f"{name} beams with pride after your praise. Confidence boosted!"

        # --- Encouragement ---
        elif topic == IndividualTalkTopic.ENCOURAGE:
            if morale < 40:
                morale_d = 6.0 * tone_mod + random.uniform(1, 3)
                rel_d = 4.0
                desc = f"{name} needed to hear that. Their spirits are visibly lifted."
            else:
                morale_d = 3.0 * tone_mod + random.uniform(0, 2)
                rel_d = 2.0
                desc = f"{name} thanks you for the kind words."

        # --- Warn behavior ---
        elif topic == IndividualTalkTopic.WARN_BEHAVIOR:
            if relationship < 30:
                morale_d = -4.0 + random.uniform(-3, 0)
                rel_d = -5.0
                desc = (
                    f"{name} doesn't take the warning well. "
                    f'"You\'ve never believed in me," they say.'
                )
            else:
                morale_d = -1.5 + random.uniform(-1, 1)
                rel_d = -1.0
                desc = f"{name} nods and promises to keep their discipline in check."

        else:
            morale_d = 0.0
            rel_d = 0.0
            desc = f"You had a brief chat with {name}."

        return morale_d, rel_d, desc


# ── Morale Trigger System ────────────────────────────────────────────────


class MoraleTriggerSystem:
    """Detects and processes automatic events that affect morale.

    Checked once per matchday/week by the season manager.
    """

    def __init__(self, session: Session):
        self.session = session

    def check_triggers(self, club_id: int, season_year: int, matchday: int) -> list[str]:
        """Check for events that automatically affect morale.

        Returns a list of human-readable trigger descriptions.
        """
        triggers: list[str] = []

        triggers.extend(self._check_streak(club_id))
        triggers.extend(self._check_league_position(club_id, season_year))
        triggers.extend(self._check_star_player_situations(club_id))
        triggers.extend(self._check_injury_crisis(club_id))
        triggers.extend(self._check_player_of_month(club_id, season_year, matchday))

        return triggers

    def _check_streak(self, club_id: int) -> list[str]:
        """Check for winning or losing streaks and adjust morale accordingly."""
        events: list[str] = []
        standing = (
            self.session.query(LeagueStanding)
            .filter_by(club_id=club_id)
            .order_by(LeagueStanding.season.desc())
            .first()
        )
        if not standing or not standing.form:
            return events

        form = standing.form
        players = self.session.query(Player).filter_by(club_id=club_id).all()

        # Winning streak: 5+ consecutive wins
        if len(form) >= 5 and form[-5:] == "WWWWW":
            for p in players:
                p.morale = min(100.0, (p.morale or 65.0) + 4.0)
            events.append("The squad is buzzing after five consecutive wins!")

        # Extended winning streak: 3-4 wins
        elif len(form) >= 3 and form[-3:] == "WWW":
            for p in players:
                p.morale = min(100.0, (p.morale or 65.0) + 2.0)
            events.append("Three wins on the bounce has lifted spirits.")

        # Losing streak: 3+ consecutive losses
        if len(form) >= 3 and form[-3:] == "LLL":
            severity = 0
            for ch in reversed(form):
                if ch == "L":
                    severity += 1
                else:
                    break

            if severity >= 5:
                for p in players:
                    p.morale = max(0.0, (p.morale or 65.0) - 8.0)
                events.append(
                    "MORALE CRISIS: Five consecutive defeats have devastated the squad."
                )
            elif severity >= 3:
                for p in players:
                    p.morale = max(0.0, (p.morale or 65.0) - 4.0)
                events.append("Confidence is draining after three consecutive defeats.")

        # Unbeaten run: no losses in last 5
        if len(form) >= 5 and "L" not in form[-5:] and form[-5:] != "WWWWW":
            for p in players:
                p.morale = min(100.0, (p.morale or 65.0) + 1.5)
            events.append("The unbeaten run continues. Confidence is growing.")

        return events

    def _check_league_position(self, club_id: int, season_year: int) -> list[str]:
        """Check if league position significantly differs from expectations."""
        events: list[str] = []

        club = self.session.get(Club, club_id)
        if not club or not club.league_id:
            return events

        standings = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=club.league_id, season=season_year)
            .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
            .all()
        )
        if not standings:
            return events

        # Find our position
        position = None
        total = len(standings)
        for i, st in enumerate(standings):
            if st.club_id == club_id:
                position = i + 1
                break

        if position is None or total < 4:
            return events

        players = self.session.query(Player).filter_by(club_id=club_id).all()

        # Top of the table boost
        if position == 1 and total >= 10:
            for p in players:
                p.morale = min(100.0, (p.morale or 65.0) + 1.5)
            events.append("Top of the table! The squad believes this could be their year.")

        # Relegation zone anxiety
        league = self.session.get(type(club.league).__class__, club.league_id) if False else None
        releg_zone = max(1, total - 3)
        if position >= releg_zone and (club.reputation or 50) > 40:
            for p in players:
                p.morale = max(0.0, (p.morale or 65.0) - 2.0)
            events.append("Relegation fears are gripping the squad.")

        return events

    def _check_star_player_situations(self, club_id: int) -> list[str]:
        """Check for star player contract or morale situations."""
        events: list[str] = []
        players = self.session.query(Player).filter_by(club_id=club_id).all()

        for p in players:
            # Star player very unhappy
            if (p.overall or 50) >= 80 and (p.morale or 65.0) < 25:
                name = p.short_name or p.name
                events.append(
                    f"Star player {name} is deeply unhappy and wants to leave."
                )

        return events

    def _check_injury_crisis(self, club_id: int) -> list[str]:
        """Check if too many players are injured."""
        events: list[str] = []
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return events

        injured_count = sum(1 for p in players if (p.injured_weeks or 0) > 0)
        total = len(players)

        if total > 0 and injured_count / total >= 0.25:
            events.append(
                f"Injury crisis! {injured_count} players are currently sidelined."
            )
            # Remaining players feel the pressure
            for p in players:
                if (p.injured_weeks or 0) == 0:
                    p.morale = max(0.0, (p.morale or 65.0) - 1.5)

        return events

    def _check_player_of_month(
        self, club_id: int, season_year: int, matchday: int
    ) -> list[str]:
        """Every 4 matchdays, pick a standout performer and boost their morale."""
        events: list[str] = []
        if matchday % 4 != 0 or matchday == 0:
            return events

        # Find the best performer from the club this season
        best_player = None
        best_rating = 0.0

        stats_list = (
            self.session.query(PlayerStats)
            .filter_by(season=season_year)
            .all()
        )
        player_ids = {
            p.id for p in self.session.query(Player).filter_by(club_id=club_id).all()
        }

        for ps in stats_list:
            if ps.player_id not in player_ids:
                continue
            if (ps.appearances or 0) < 2:
                continue
            rating = ps.avg_rating or 6.0
            if rating > best_rating:
                best_rating = rating
                best_player = ps.player_id

        if best_player and best_rating >= 7.0:
            player = self.session.get(Player, best_player)
            if player:
                name = player.short_name or player.name
                player.morale = min(100.0, (player.morale or 65.0) + 6.0)
                player.form = min(100.0, (player.form or 65.0) + 3.0)
                events.append(f"{name} has been outstanding and earns Player of the Month!")

        return events


# ── Main Morale Manager ──────────────────────────────────────────────────


class MoraleManager:
    """Manages player and team morale, integrating all sub-systems."""

    def __init__(self, session: Session):
        self.session = session
        self.spirit_mgr = TeamSpiritManager(session)
        self.relationship_mgr = ManagerRelationship(session)
        self.individual_mgr = IndividualTalkManager(session, self.relationship_mgr)
        self.trigger_system = MoraleTriggerSystem(session)

    # ── Team talks ─────────────────────────────────────────────────────────

    def give_team_talk(
        self,
        club_id: int,
        talk_type: TeamTalkType,
        context: str = "pre_match",
    ):
        """Apply a team talk. Effects depend on context and team state.

        - MOTIVATE when losing: boost morale, slight fitness cost
        - CALM when winning big: maintain focus
        - PRAISE after win: boost morale significantly
        - CRITICIZE after loss: risky - can boost or tank morale
        - Right talk at right time = big boost
        - Wrong talk = morale drops
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return

        avg_morale = sum(p.morale or 65.0 for p in players) / len(players)

        for player in players:
            delta = self._calculate_talk_effect(
                talk_type, context, avg_morale, player
            )
            player.morale = max(0.0, min(100.0, (player.morale or 65.0) + delta))

            # Motivational and passionate talks cost a bit of energy
            if talk_type in (TeamTalkType.MOTIVATE, TeamTalkType.PASSIONATE):
                player.fitness = max(
                    0.0, (player.fitness or 100.0) - random.uniform(0.5, 1.5)
                )

        self.session.flush()

    def process_match_result(
        self,
        club_id: int,
        goals_for: int,
        goals_against: int,
        was_home: bool,
        opponent_reputation: int,
    ):
        """Update morale based on match result.

        Beating a stronger team = big morale boost.
        Losing to weaker team = morale drop.
        """
        club = self.session.query(Club).get(club_id)
        if not club:
            return

        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return

        club_rep = club.reputation or 50
        opp_rep = opponent_reputation or 50
        rep_diff = opp_rep - club_rep  # positive = opponent is stronger

        goal_diff = goals_for - goals_against

        if goal_diff > 0:
            # Win
            base_boost = 4.0 + min(goal_diff * 1.5, 6.0)
            # Bigger boost for beating stronger opponents
            if rep_diff > 10:
                base_boost += rep_diff * 0.15
            # Smaller boost for beating much weaker teams
            elif rep_diff < -20:
                base_boost *= 0.6
        elif goal_diff == 0:
            # Draw
            if rep_diff > 15:
                base_boost = 2.0  # Good draw against stronger team
            elif rep_diff < -15:
                base_boost = -3.0  # Bad draw against weaker team
            else:
                base_boost = 0.0
        else:
            # Loss
            base_boost = -4.0 - min(abs(goal_diff) * 1.5, 8.0)
            # Losing to weaker team hurts more
            if rep_diff < -10:
                base_boost += rep_diff * 0.1  # rep_diff is negative, so worse
            # Losing to much stronger team is more acceptable
            elif rep_diff > 20:
                base_boost *= 0.5

        # Home/away modifier
        if was_home and goal_diff < 0:
            base_boost -= 1.5  # Home loss stings more
        elif not was_home and goal_diff > 0:
            base_boost += 1.5  # Away win feels better

        # Team spirit modifier
        spirit = self.spirit_mgr.calculate_team_spirit(club_id)
        spirit_mod = (spirit - 50.0) / 100.0  # -0.5 to +0.5
        if goal_diff > 0:
            base_boost *= (1.0 + spirit_mod * 0.3)  # Good spirit amplifies wins
        elif goal_diff < 0:
            base_boost *= (1.0 - spirit_mod * 0.2)  # Good spirit cushions losses

        for player in players:
            # Individual variation
            variation = random.uniform(-1.5, 1.5)
            delta = base_boost + variation

            # Players with high composure are more stable
            composure = (player.composure or 50) / 100.0
            delta *= (1.0 - composure * 0.3)

            # Relationship affects how they respond to results
            rel = self.relationship_mgr.get_relationship(player.id)
            if rel < 30 and goal_diff < 0:
                delta *= 1.3  # Unhappy players take losses harder
            elif rel > 75 and goal_diff > 0:
                delta *= 1.15  # Close to manager, enjoy wins more

            player.morale = max(0.0, min(100.0, (player.morale or 65.0) + delta))

            # Form adjustment based on result
            if goal_diff > 0:
                player.form = min(
                    100.0, (player.form or 65.0) + random.uniform(1.0, 3.0)
                )
            elif goal_diff < 0:
                player.form = max(
                    0.0, (player.form or 65.0) - random.uniform(1.0, 3.0)
                )

        self.session.flush()

    def get_team_morale(self, club_id: int) -> dict:
        """Return team morale summary.

        Returns a dict with average morale, category label, per-player
        breakdown counts, team spirit info, and unhappy player count.
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return {
                "average": 0.0,
                "label": "Unknown",
                "very_happy": 0,
                "happy": 0,
                "content": 0,
                "unhappy": 0,
                "very_unhappy": 0,
                "player_count": 0,
                "team_spirit": 50.0,
                "spirit_level": TeamSpiritLevel.DECENT.value,
                "spirit_description": "",
                "unhappy_with_manager": 0,
            }

        morales = [(p.morale or 65.0) for p in players]
        avg = sum(morales) / len(morales)

        # Categorise each player
        very_happy = sum(1 for m in morales if m >= 85)
        happy = sum(1 for m in morales if 70 <= m < 85)
        content = sum(1 for m in morales if 50 <= m < 70)
        unhappy = sum(1 for m in morales if 30 <= m < 50)
        very_unhappy = sum(1 for m in morales if m < 30)

        label = _morale_label(avg)

        # Team spirit
        spirit = self.spirit_mgr.calculate_team_spirit(club_id)
        spirit_level = self.spirit_mgr.get_spirit_level(club_id)
        spirit_effects = self.spirit_mgr.get_spirit_effects(club_id)

        # Unhappy with manager count
        unhappy_with_mgr = len(self.relationship_mgr.get_unhappy_players(club_id))

        return {
            "average": round(avg, 1),
            "label": label,
            "very_happy": very_happy,
            "happy": happy,
            "content": content,
            "unhappy": unhappy,
            "very_unhappy": very_unhappy,
            "player_count": len(players),
            "team_spirit": round(spirit, 1),
            "spirit_level": spirit_level.value,
            "spirit_description": spirit_effects.get("description", ""),
            "unhappy_with_manager": unhappy_with_mgr,
        }

    def process_weekly_morale(self, club_id: int, season_year: int, matchday: int) -> list[str]:
        """Run all weekly morale processing for a club.

        Called by SeasonManager during _process_weekly.
        Returns list of event descriptions.
        """
        events: list[str] = []

        # 1. Check automatic triggers
        triggers = self.trigger_system.check_triggers(club_id, season_year, matchday)
        events.extend(triggers)

        # 2. Check promises
        promise_events = self.relationship_mgr.check_promises(
            club_id, matchday, season_year
        )
        events.extend(promise_events)

        # 3. Natural morale regression toward 60 (mild)
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        for p in players:
            morale = p.morale or 65.0
            if morale > 70:
                p.morale = morale - random.uniform(0.3, 0.8)
            elif morale < 45:
                p.morale = morale + random.uniform(0.3, 0.8)

        # 4. Recalculate team spirit
        self.spirit_mgr.calculate_team_spirit(club_id)

        self.session.flush()
        return events

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _calculate_talk_effect(
        talk_type: TeamTalkType,
        context: str,
        avg_morale: float,
        player: Player,
    ) -> float:
        """Calculate morale delta for a single player from a team talk."""
        composure = (player.composure or 50) / 100.0
        big_match = (player.big_match or 65) / 100.0

        if context == "pre_match":
            return _pre_match_effect(talk_type, avg_morale, composure, big_match)
        elif context == "post_match_win":
            return _post_match_win_effect(talk_type, avg_morale, composure)
        elif context == "post_match_loss":
            return _post_match_loss_effect(talk_type, avg_morale, composure)
        elif context == "post_match_draw":
            return _post_match_draw_effect(talk_type, avg_morale, composure)
        elif context == "half_time":
            return _half_time_effect(talk_type, avg_morale, composure, big_match)
        else:
            return _pre_match_effect(talk_type, avg_morale, composure, big_match)


# ── Talk-effect calculators ───────────────────────────────────────────────


def _pre_match_effect(
    talk_type: TeamTalkType,
    avg_morale: float,
    composure: float,
    big_match: float,
) -> float:
    """Calculate morale change for a pre-match talk."""
    if talk_type == TeamTalkType.MOTIVATE:
        base = 5.0 if avg_morale < 60 else 2.0
        return base * big_match + random.uniform(-1, 1)
    elif talk_type == TeamTalkType.CALM:
        if avg_morale > 80:
            return 2.0 + random.uniform(0, 1)
        elif avg_morale < 40:
            return 3.0 * composure + random.uniform(0, 1)
        return random.uniform(-1, 1)
    elif talk_type == TeamTalkType.FOCUS:
        return 2.0 * composure + random.uniform(0, 2)
    elif talk_type == TeamTalkType.NO_PRESSURE:
        if avg_morale < 50:
            return 4.0 + random.uniform(0, 2)
        return random.uniform(-2, 1)
    elif talk_type == TeamTalkType.PRAISE:
        return random.uniform(0, 2)
    elif talk_type == TeamTalkType.CRITICIZE:
        if random.random() < 0.4:
            return 3.0
        return -4.0 + random.uniform(-2, 0)
    elif talk_type == TeamTalkType.DEMAND_MORE:
        # Effective when team is coasting, risky if morale is low
        if avg_morale > 60:
            return 3.5 * big_match + random.uniform(0, 2)
        elif avg_morale < 40:
            return -3.0 + random.uniform(-2, 0)
        return 1.5 + random.uniform(-1, 1)
    elif talk_type == TeamTalkType.SHOW_FAITH:
        # Always positive, bigger boost for low morale
        if avg_morale < 50:
            return 5.0 + random.uniform(1, 3)
        return 2.5 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.PASSIONATE:
        # High variance: can really fire up or fall flat
        if random.random() < 0.65:
            return 5.0 * big_match + random.uniform(1, 3)
        return -1.0 + random.uniform(-2, 1)
    elif talk_type == TeamTalkType.ANALYTICAL:
        # Consistent but moderate, works well with composed players
        return 2.0 * composure + 1.5 + random.uniform(-0.5, 1)
    return 0.0


def _post_match_win_effect(
    talk_type: TeamTalkType,
    avg_morale: float,
    composure: float,
) -> float:
    """Calculate morale change after a win."""
    if talk_type == TeamTalkType.PRAISE:
        return 5.0 + random.uniform(1, 3)
    elif talk_type == TeamTalkType.CALM:
        return 2.0 + random.uniform(0, 1)
    elif talk_type == TeamTalkType.FOCUS:
        return 2.0 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.MOTIVATE:
        return 1.5 + random.uniform(0, 1)
    elif talk_type == TeamTalkType.CRITICIZE:
        return -6.0 + random.uniform(-2, 0)
    elif talk_type == TeamTalkType.NO_PRESSURE:
        return random.uniform(0, 2)
    elif talk_type == TeamTalkType.DEMAND_MORE:
        # After a win, demanding more can be seen as ungrateful
        if avg_morale > 75:
            return 1.0 + random.uniform(-1, 1)  # accepted if confident
        return -2.5 + random.uniform(-1, 1)
    elif talk_type == TeamTalkType.SHOW_FAITH:
        return 4.0 + random.uniform(1, 2)
    elif talk_type == TeamTalkType.PASSIONATE:
        return 4.5 + random.uniform(0, 3)
    elif talk_type == TeamTalkType.ANALYTICAL:
        return 2.5 + random.uniform(0, 1.5)
    return 0.0


def _post_match_loss_effect(
    talk_type: TeamTalkType,
    avg_morale: float,
    composure: float,
) -> float:
    """Calculate morale change after a loss."""
    if talk_type == TeamTalkType.MOTIVATE:
        return 3.0 + random.uniform(0, 3)
    elif talk_type == TeamTalkType.NO_PRESSURE:
        return 3.0 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.CRITICIZE:
        if random.random() < 0.35:
            return 4.0 + random.uniform(0, 2)
        return -5.0 + random.uniform(-3, 0)
    elif talk_type == TeamTalkType.CALM:
        if avg_morale < 40:
            return 2.0 + random.uniform(0, 2)
        return random.uniform(-1, 1)
    elif talk_type == TeamTalkType.PRAISE:
        return -3.0 + random.uniform(-2, 0)
    elif talk_type == TeamTalkType.FOCUS:
        return 1.0 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.DEMAND_MORE:
        # After a loss, demanding more is risky
        if random.random() < 0.4:
            return 3.5 + random.uniform(0, 2)  # Fired up
        return -4.0 + random.uniform(-2, 0)
    elif talk_type == TeamTalkType.SHOW_FAITH:
        # Excellent after a loss - shows trust
        return 5.0 + random.uniform(1, 3)
    elif talk_type == TeamTalkType.PASSIONATE:
        if random.random() < 0.5:
            return 4.0 + random.uniform(1, 3)
        return -1.0 + random.uniform(-2, 1)
    elif talk_type == TeamTalkType.ANALYTICAL:
        # Calm analysis after a loss - composed players respond well
        return 2.0 * composure + 1.0 + random.uniform(0, 2)
    return 0.0


def _post_match_draw_effect(
    talk_type: TeamTalkType,
    avg_morale: float,
    composure: float,
) -> float:
    """Calculate morale change after a draw."""
    if talk_type == TeamTalkType.MOTIVATE:
        return 2.5 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.FOCUS:
        return 2.0 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.CALM:
        return 1.5 + random.uniform(0, 1.5)
    elif talk_type == TeamTalkType.PRAISE:
        if avg_morale < 50:
            return 3.0 + random.uniform(0, 2)
        return random.uniform(-1, 1)
    elif talk_type == TeamTalkType.NO_PRESSURE:
        return 1.5 + random.uniform(0, 1.5)
    elif talk_type == TeamTalkType.CRITICIZE:
        if random.random() < 0.3:
            return 2.0 + random.uniform(0, 1.5)
        return -3.0 + random.uniform(-2, 0)
    elif talk_type == TeamTalkType.DEMAND_MORE:
        return 2.0 + random.uniform(-1, 2)
    elif talk_type == TeamTalkType.SHOW_FAITH:
        return 3.0 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.PASSIONATE:
        if random.random() < 0.55:
            return 3.5 + random.uniform(0, 2)
        return -0.5 + random.uniform(-1, 1)
    elif talk_type == TeamTalkType.ANALYTICAL:
        return 2.0 * composure + 1.0 + random.uniform(0, 1)
    return 0.0


def _half_time_effect(
    talk_type: TeamTalkType,
    avg_morale: float,
    composure: float,
    big_match: float,
) -> float:
    """Calculate morale change for a half-time talk."""
    if talk_type == TeamTalkType.MOTIVATE:
        base = 4.0 if avg_morale < 55 else 1.5
        return base * big_match + random.uniform(-0.5, 1.5)
    elif talk_type == TeamTalkType.CALM:
        return 2.0 * composure + random.uniform(0, 1.5)
    elif talk_type == TeamTalkType.FOCUS:
        return 2.5 * composure + random.uniform(0, 1)
    elif talk_type == TeamTalkType.CRITICIZE:
        if random.random() < 0.3:
            return 3.5
        return -3.5 + random.uniform(-1.5, 0)
    elif talk_type == TeamTalkType.PRAISE:
        return 2.0 + random.uniform(0, 1.5)
    elif talk_type == TeamTalkType.NO_PRESSURE:
        return 2.5 if avg_morale < 45 else random.uniform(-0.5, 1.5)
    elif talk_type == TeamTalkType.DEMAND_MORE:
        if avg_morale > 50:
            return 3.0 * big_match + random.uniform(0, 2)
        return -2.0 + random.uniform(-1, 1)
    elif talk_type == TeamTalkType.SHOW_FAITH:
        return 3.0 + random.uniform(0, 2)
    elif talk_type == TeamTalkType.PASSIONATE:
        # Passionate half-time talks can be game-changers
        if random.random() < 0.6:
            return 5.0 * big_match + random.uniform(1, 2)
        return random.uniform(-1, 1)
    elif talk_type == TeamTalkType.ANALYTICAL:
        return 2.5 * composure + 1.0 + random.uniform(0, 1)
    return 0.0


def _morale_label(avg: float) -> str:
    """Return a human-readable morale label."""
    if avg >= 85:
        return "Superb"
    elif avg >= 70:
        return "Good"
    elif avg >= 55:
        return "Decent"
    elif avg >= 40:
        return "Poor"
    elif avg >= 25:
        return "Very Poor"
    return "Abysmal"
