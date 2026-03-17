"""Player interactions, dressing room dynamics, and happiness management.

Manages player happiness, complaints, transfer requests, squad roles,
inter-player relationships, chemistry, mentoring, cliques, and overall
dressing room atmosphere.  Integrates with morale but tracks deeper
motivational factors that evolve over weeks of play.
"""
from __future__ import annotations

import enum
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from fm.db.models import Club, Player, PlayerStats, NewsItem, Season


# ── Enums ─────────────────────────────────────────────────────────────────

class SquadRole(str, enum.Enum):
    KEY_PLAYER = "key_player"
    FIRST_TEAM = "first_team"
    ROTATION = "rotation"
    BACKUP = "backup"
    YOUTH = "youth"
    NOT_NEEDED = "not_needed"


class PlayingTimeExpectation(str, enum.Enum):
    REGULAR_STARTER = "regular_starter"   # >75% of minutes
    IMPORTANT_PLAYER = "important_player" # 50-75%
    SQUAD_ROTATION = "squad_rotation"     # 25-50%
    BACKUP = "backup"                     # <25%
    YOUTH_PROSPECT = "youth_prospect"     # any minutes are a bonus


class ComplaintType(str, enum.Enum):
    PLAYING_TIME = "playing_time"
    NEW_CONTRACT = "new_contract"
    BIGGER_CLUB = "bigger_club"
    UNHAPPY_TRAINING = "unhappy_training"
    WANTS_TO_LEAVE = "wants_to_leave"
    CAPTAIN_DISPUTE = "captain_dispute"


class ComplaintResponse(str, enum.Enum):
    PROMISE_GAME_TIME = "promise_game_time"
    IMPORTANT_MEMBER = "important_member"
    CONSIDER_SELLING = "consider_selling"
    GOING_NOWHERE = "going_nowhere"
    DISCUSS_CONTRACT = "discuss_contract"
    WILL_REVIEW = "will_review"


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class HappinessFactors:
    """All factors influencing a single player's happiness."""
    playing_time: float = 0.0        # -20 to +20
    squad_role_match: float = 0.0    # -15 to +15
    wage_satisfaction: float = 0.0   # -10 to +10
    team_performance: float = 0.0    # -10 to +10
    personal_form: float = 0.0       # -10 to +10
    relationship_with_manager: float = 0.0  # -15 to +15
    training_satisfaction: float = 0.0      # -5 to +5
    transfer_request_pending: bool = False

    @property
    def total(self) -> float:
        """Aggregate happiness modifier (clamped to -100..+100)."""
        raw = (self.playing_time + self.squad_role_match +
               self.wage_satisfaction + self.team_performance +
               self.personal_form + self.relationship_with_manager +
               self.training_satisfaction)
        if self.transfer_request_pending:
            raw -= 15.0
        return max(-100.0, min(100.0, raw))


@dataclass
class PlayerComplaint:
    """A complaint raised by a player that requires a manager response."""
    complaint_id: int
    player_id: int
    player_name: str
    complaint_type: ComplaintType
    message: str
    severity: float  # 0-1, higher = more urgent
    available_responses: list[ComplaintResponse] = field(default_factory=list)


@dataclass
class Relationship:
    """A relationship between two players."""
    player_a_id: int
    player_b_id: int
    chemistry: float = 50.0  # 0-100
    is_mentor: bool = False   # a mentors b
    is_conflict: bool = False


# ── In-memory state stores (per club) ─────────────────────────────────────
# These are rebuilt each time the manager is instantiated from the session.
# For a full save/load they could be serialised to the DB, but for now they
# live in memory and are deterministically reconstructed.

_squad_roles: dict[int, SquadRole] = {}          # player_id -> role
_happiness: dict[int, HappinessFactors] = {}     # player_id -> factors
_relationships: dict[tuple[int, int], Relationship] = {}  # (a,b) sorted -> rel
_complaints: dict[int, PlayerComplaint] = {}     # complaint_id -> complaint
_promises: dict[int, dict] = {}                  # player_id -> {type, matchday}
_transfer_requests: set[int] = set()             # player_ids requesting out
_next_complaint_id: int = 1


# ── Complaint templates ───────────────────────────────────────────────────

_COMPLAINT_MESSAGES: dict[ComplaintType, list[str]] = {
    ComplaintType.PLAYING_TIME: [
        "Boss, I'm not getting enough game time. I need to play more.",
        "I came here to play, not to watch from the bench every week.",
        "My career is stalling. I need regular football.",
    ],
    ComplaintType.NEW_CONTRACT: [
        "I think I've earned a better deal. Can we discuss a new contract?",
        "My contract's running down and I'd like some security.",
        "I'm being paid less than players below my level. That's not right.",
    ],
    ComplaintType.BIGGER_CLUB: [
        "I've outgrown this club. I think it's time for a step up.",
        "I appreciate everything here, but I want to compete at the top.",
        "With respect, I think I should be playing for a bigger club.",
    ],
    ComplaintType.UNHAPPY_TRAINING: [
        "Training isn't helping me develop. We need a change.",
        "I feel like I'm going backwards in these sessions.",
        "The training programme doesn't suit my abilities at all.",
    ],
    ComplaintType.WANTS_TO_LEAVE: [
        "I want to leave. Please accept any reasonable offer for me.",
        "I'm sorry, but I need a fresh start somewhere else.",
        "Things aren't working out. I want to submit a transfer request.",
    ],
    ComplaintType.CAPTAIN_DISPUTE: [
        "I don't think the current captain is leading this team well.",
        "The armband should go to someone who actually inspires the squad.",
        "We need a captain who leads by example on the pitch.",
    ],
}

_VALID_RESPONSES: dict[ComplaintType, list[ComplaintResponse]] = {
    ComplaintType.PLAYING_TIME: [
        ComplaintResponse.PROMISE_GAME_TIME,
        ComplaintResponse.IMPORTANT_MEMBER,
        ComplaintResponse.CONSIDER_SELLING,
    ],
    ComplaintType.NEW_CONTRACT: [
        ComplaintResponse.DISCUSS_CONTRACT,
        ComplaintResponse.IMPORTANT_MEMBER,
        ComplaintResponse.GOING_NOWHERE,
    ],
    ComplaintType.BIGGER_CLUB: [
        ComplaintResponse.GOING_NOWHERE,
        ComplaintResponse.CONSIDER_SELLING,
        ComplaintResponse.IMPORTANT_MEMBER,
    ],
    ComplaintType.UNHAPPY_TRAINING: [
        ComplaintResponse.WILL_REVIEW,
        ComplaintResponse.IMPORTANT_MEMBER,
        ComplaintResponse.GOING_NOWHERE,
    ],
    ComplaintType.WANTS_TO_LEAVE: [
        ComplaintResponse.CONSIDER_SELLING,
        ComplaintResponse.GOING_NOWHERE,
        ComplaintResponse.IMPORTANT_MEMBER,
    ],
    ComplaintType.CAPTAIN_DISPUTE: [
        ComplaintResponse.WILL_REVIEW,
        ComplaintResponse.GOING_NOWHERE,
        ComplaintResponse.IMPORTANT_MEMBER,
    ],
}


# ══════════════════════════════════════════════════════════════════════════
#  PlayerDynamicsManager
# ══════════════════════════════════════════════════════════════════════════

class PlayerDynamicsManager:
    """Manages player happiness, complaints, squad roles, and transfer requests."""

    def __init__(self, session: Session):
        self.session = session

    # ── Weekly processing ─────────────────────────────────────────────────

    def process_weekly_happiness(self, club_id: int) -> list[PlayerComplaint]:
        """Evaluate every player's happiness and generate complaints.

        Called once per matchday cycle, before the next match.  Returns any
        new complaints that need the human manager's attention.
        """
        club = self.session.query(Club).get(club_id)
        if not club:
            return []

        season = self._current_season()
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        new_complaints: list[PlayerComplaint] = []

        for player in players:
            factors = self._evaluate_happiness(player, club, season)
            _happiness[player.id] = factors

            # Apply happiness to morale (soft influence)
            happiness_mod = factors.total * 0.05  # -5 to +5 per week
            player.morale = max(0.0, min(100.0, (player.morale or 65.0) + happiness_mod))

            # Check for complaints
            complaint = self._maybe_generate_complaint(player, factors, club)
            if complaint:
                new_complaints.append(complaint)

        # Check broken promises
        broken = self._check_promises(club_id, season)
        new_complaints.extend(broken)

        self.session.flush()
        return new_complaints

    def check_player_complaints(self, club_id: int) -> list[PlayerComplaint]:
        """Return all pending complaints for the club."""
        player_ids = {
            p.id for p in
            self.session.query(Player.id).filter_by(club_id=club_id).all()
        }
        return [
            c for c in _complaints.values()
            if c.player_id in player_ids
        ]

    def respond_to_complaint(
        self, complaint_id: int, response: ComplaintResponse
    ) -> str:
        """Handle a manager's response to a player complaint.

        Returns a human-readable outcome string.
        """
        complaint = _complaints.pop(complaint_id, None)
        if not complaint:
            return "No such complaint."

        player = self.session.query(Player).get(complaint.player_id)
        if not player:
            return "Player not found."

        ct = complaint.complaint_type
        outcome = self._apply_response(player, ct, response)
        self.session.flush()
        return outcome

    # ── Playing time ──────────────────────────────────────────────────────

    def get_playing_time_expectation(self, player: Player) -> PlayingTimeExpectation:
        """Derive what a player expects based on age, ability, and role."""
        role = _squad_roles.get(player.id)
        if role:
            return _role_to_expectation(role)

        # Auto-detect from ability relative to squad
        squad = self.session.query(Player).filter_by(club_id=player.club_id).all()
        if not squad:
            return PlayingTimeExpectation.SQUAD_ROTATION

        overalls = sorted((p.overall or 50 for p in squad), reverse=True)
        rank = next(
            (i for i, v in enumerate(overalls) if v <= (player.overall or 50)),
            len(overalls),
        )

        if rank < 11:
            return PlayingTimeExpectation.REGULAR_STARTER
        elif rank < 16:
            return PlayingTimeExpectation.IMPORTANT_PLAYER
        elif rank < 22:
            return PlayingTimeExpectation.SQUAD_ROTATION
        elif (player.age or 25) < 21:
            return PlayingTimeExpectation.YOUTH_PROSPECT
        else:
            return PlayingTimeExpectation.BACKUP

    def check_playing_time_satisfaction(self, player_id: int) -> float:
        """Return a -20..+20 score for playing time satisfaction."""
        player = self.session.query(Player).get(player_id)
        if not player:
            return 0.0

        season = self._current_season()
        stats = self.session.query(PlayerStats).filter_by(
            player_id=player_id, season=season.year
        ).first()

        minutes = stats.minutes_played if stats else 0
        matches_played = season.current_matchday or 1
        max_minutes = matches_played * 90
        pct = (minutes / max_minutes * 100) if max_minutes > 0 else 0

        expectation = self.get_playing_time_expectation(player)
        thresholds = {
            PlayingTimeExpectation.REGULAR_STARTER: 75,
            PlayingTimeExpectation.IMPORTANT_PLAYER: 50,
            PlayingTimeExpectation.SQUAD_ROTATION: 25,
            PlayingTimeExpectation.BACKUP: 10,
            PlayingTimeExpectation.YOUTH_PROSPECT: 5,
        }
        target = thresholds.get(expectation, 25)

        if pct >= target:
            return min(20.0, (pct - target) * 0.4)
        else:
            deficit = target - pct
            return max(-20.0, -deficit * 0.5)

    # ── Transfer requests ─────────────────────────────────────────────────

    def player_requests_transfer(self, player_id: int) -> bool:
        """Check if a player should request a transfer. Returns True if new request."""
        if player_id in _transfer_requests:
            return False

        player = self.session.query(Player).get(player_id)
        if not player:
            return False

        factors = _happiness.get(player_id)
        if not factors:
            return False

        # Unhappy players with low morale may request a transfer
        if factors.total < -30 and (player.morale or 65) < 40:
            chance = 0.15 + abs(factors.total) * 0.005
            if random.random() < chance:
                _transfer_requests.add(player_id)
                factors.transfer_request_pending = True

                club = self.session.query(Club).get(player.club_id)
                club_name = club.name if club else "their club"
                season = self._current_season()
                self.session.add(NewsItem(
                    season=season.year,
                    matchday=season.current_matchday,
                    headline=f"{player.short_name or player.name} requests transfer!",
                    body=f"{player.name} has submitted a transfer request at {club_name} "
                         f"after growing unhappy with the situation.",
                    category="transfer",
                ))
                self.session.flush()
                return True
        return False

    def respond_to_transfer_request(self, player_id: int, accept: bool) -> str:
        """Respond to a transfer request.  accept=True lists the player."""
        player = self.session.query(Player).get(player_id)
        if not player:
            return "Player not found."

        if accept:
            _transfer_requests.discard(player_id)
            factors = _happiness.get(player_id)
            if factors:
                factors.transfer_request_pending = False
                factors.relationship_with_manager += 5.0
            player.morale = min(100.0, (player.morale or 65.0) + 10.0)
            self.session.flush()
            return (f"{player.short_name or player.name} is relieved you've agreed "
                    f"to let them go. They'll be available for transfer.")
        else:
            # Refusing can go two ways
            composure = (player.composure or 50) / 100.0
            if random.random() < 0.3 + composure * 0.3:
                # Accepts decision grudgingly
                _transfer_requests.discard(player_id)
                factors = _happiness.get(player_id)
                if factors:
                    factors.transfer_request_pending = False
                    factors.relationship_with_manager -= 5.0
                player.morale = max(0.0, (player.morale or 65.0) - 5.0)
                self.session.flush()
                return (f"{player.short_name or player.name} is disappointed but "
                        f"has withdrawn their transfer request.")
            else:
                # Continues to agitate
                player.morale = max(0.0, (player.morale or 65.0) - 10.0)
                factors = _happiness.get(player_id)
                if factors:
                    factors.relationship_with_manager -= 10.0
                self.session.flush()
                return (f"{player.short_name or player.name} is furious and insists "
                        f"they still want to leave.")

    # ── Squad role management ─────────────────────────────────────────────

    def set_squad_role(self, player_id: int, role: SquadRole) -> str:
        """Assign a squad role. Returns outcome message."""
        player = self.session.query(Player).get(player_id)
        if not player:
            return "Player not found."

        old_role = _squad_roles.get(player_id)
        _squad_roles[player_id] = role
        name = player.short_name or player.name

        # Reaction depends on whether role matches ability
        expected = self._expected_role(player)
        if role.value == expected.value:
            return f"{name} is happy with their role as {_role_label(role)}."
        elif _role_rank(role) > _role_rank(expected):
            # Promoted beyond expectations
            player.morale = min(100.0, (player.morale or 65.0) + 5.0)
            self.session.flush()
            return f"{name} is delighted to be considered a {_role_label(role)}!"
        else:
            # Demoted
            player.morale = max(0.0, (player.morale or 65.0) - 8.0)
            self.session.flush()
            return f"{name} is unhappy about being designated as {_role_label(role)}."

    def get_squad_hierarchy(self, club_id: int) -> dict[str, list[dict]]:
        """Return players grouped by squad role."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        hierarchy: dict[str, list[dict]] = {r.value: [] for r in SquadRole}

        for p in players:
            role = _squad_roles.get(p.id, self._expected_role(p))
            hierarchy[role.value].append({
                "id": p.id,
                "name": p.short_name or p.name,
                "overall": p.overall,
                "position": p.position,
                "morale": p.morale,
            })

        return hierarchy

    # ── Internal helpers ──────────────────────────────────────────────────

    def _current_season(self) -> Season:
        return self.session.query(Season).order_by(Season.year.desc()).first()

    def _evaluate_happiness(
        self, player: Player, club: Club, season: Season
    ) -> HappinessFactors:
        """Build a complete HappinessFactors snapshot for a player."""
        factors = _happiness.get(player.id, HappinessFactors())

        # 1. Playing time
        factors.playing_time = self.check_playing_time_satisfaction(player.id)

        # 2. Squad role match
        assigned = _squad_roles.get(player.id)
        expected = self._expected_role(player)
        if assigned:
            diff = _role_rank(assigned) - _role_rank(expected)
            factors.squad_role_match = max(-15.0, min(15.0, diff * 5.0))
        else:
            factors.squad_role_match = 0.0

        # 3. Wage satisfaction
        squad = self.session.query(Player).filter_by(club_id=club.id).all()
        if squad:
            avg_wage = sum(p.wage or 0 for p in squad) / len(squad)
            if avg_wage > 0:
                ratio = (player.wage or 0) / avg_wage
                # Stars expect to be paid more than average
                ability_ratio = (player.overall or 50) / max(
                    1, sum(p.overall or 50 for p in squad) / len(squad)
                )
                wage_gap = ratio - ability_ratio
                factors.wage_satisfaction = max(-10.0, min(10.0, wage_gap * 10.0))
            else:
                factors.wage_satisfaction = 0.0

        # 4. Team performance (form string from standings)
        from fm.db.models import LeagueStanding
        standing = self.session.query(LeagueStanding).filter_by(
            club_id=club.id, season=season.year
        ).first()
        if standing and standing.form:
            wins = standing.form.count("W")
            losses = standing.form.count("L")
            form_len = max(len(standing.form), 1)
            factors.team_performance = ((wins - losses) / form_len) * 10.0

        # 5. Personal form
        pf = (player.form or 65.0)
        factors.personal_form = (pf - 65.0) * 0.3  # centered around 65

        # 6. Relationship with manager -- persistent, modified by responses
        #    (keep existing value, just clamp)
        factors.relationship_with_manager = max(
            -15.0, min(15.0, factors.relationship_with_manager)
        )

        # 7. Training satisfaction -- random small factor
        factors.training_satisfaction = random.uniform(-2.0, 2.0)

        # 8. Transfer request flag
        factors.transfer_request_pending = player.id in _transfer_requests

        return factors

    def _maybe_generate_complaint(
        self, player: Player, factors: HappinessFactors, club: Club
    ) -> Optional[PlayerComplaint]:
        """Probabilistically generate a complaint based on unhappiness."""
        global _next_complaint_id

        # Don't spam -- max one complaint per player in the queue
        if any(c.player_id == player.id for c in _complaints.values()):
            return None

        # Only unhappy players complain
        total = factors.total
        if total > -10:
            return None

        # Probability scales with unhappiness
        prob = min(0.35, abs(total) * 0.005)
        if random.random() > prob:
            return None

        # Pick the most relevant complaint type
        ct = self._pick_complaint_type(player, factors, club)
        if ct is None:
            return None

        severity = min(1.0, abs(total) / 60.0)
        msg = random.choice(_COMPLAINT_MESSAGES[ct])
        responses = _VALID_RESPONSES.get(ct, [ComplaintResponse.WILL_REVIEW])

        complaint = PlayerComplaint(
            complaint_id=_next_complaint_id,
            player_id=player.id,
            player_name=player.short_name or player.name,
            complaint_type=ct,
            message=msg,
            severity=severity,
            available_responses=list(responses),
        )
        _complaints[_next_complaint_id] = complaint
        _next_complaint_id += 1
        return complaint

    def _pick_complaint_type(
        self, player: Player, factors: HappinessFactors, club: Club
    ) -> Optional[ComplaintType]:
        """Select the most pressing complaint type for a player."""
        candidates: list[tuple[float, ComplaintType]] = []

        if factors.playing_time < -10:
            candidates.append((abs(factors.playing_time), ComplaintType.PLAYING_TIME))

        # Contract running out
        season = self._current_season()
        years_left = (player.contract_expiry or 2026) - season.year
        if years_left <= 1 or factors.wage_satisfaction < -5:
            urgency = 15.0 if years_left <= 1 else abs(factors.wage_satisfaction)
            candidates.append((urgency, ComplaintType.NEW_CONTRACT))

        # Ambitious player at smaller club
        if (player.overall or 50) > (club.reputation or 50) + 15:
            candidates.append((10.0, ComplaintType.BIGGER_CLUB))

        if factors.training_satisfaction < -3:
            candidates.append((5.0, ComplaintType.UNHAPPY_TRAINING))

        if factors.total < -35:
            candidates.append((abs(factors.total), ComplaintType.WANTS_TO_LEAVE))

        if not candidates:
            return None

        # Weighted random from top candidates
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def _apply_response(
        self, player: Player, ct: ComplaintType, response: ComplaintResponse
    ) -> str:
        """Apply the effect of a manager response and return outcome text."""
        name = player.short_name or player.name
        factors = _happiness.get(player.id, HappinessFactors())
        season = self._current_season()

        if response == ComplaintResponse.PROMISE_GAME_TIME:
            _promises[player.id] = {
                "type": "game_time",
                "matchday": season.current_matchday or 0,
            }
            factors.relationship_with_manager += 5.0
            player.morale = min(100.0, (player.morale or 65.0) + 8.0)
            self.session.flush()
            return (f"{name} appreciates the promise. They'll expect to see "
                    f"regular action in the coming weeks.")

        elif response == ComplaintResponse.IMPORTANT_MEMBER:
            boost = random.uniform(3.0, 7.0)
            player.morale = min(100.0, (player.morale or 65.0) + boost)
            factors.relationship_with_manager += 2.0
            self.session.flush()
            return f"{name} feels valued, though they'll want to see it reflected on the pitch."

        elif response == ComplaintResponse.CONSIDER_SELLING:
            _transfer_requests.add(player.id)
            factors.transfer_request_pending = True
            player.morale = min(100.0, (player.morale or 65.0) + 5.0)
            self.session.flush()
            return f"{name} appreciates your honesty. They'll hope a move materialises."

        elif response == ComplaintResponse.GOING_NOWHERE:
            composure = (player.composure or 50) / 100.0
            if random.random() < 0.3 + composure * 0.2:
                # Accepts it
                factors.relationship_with_manager -= 3.0
                player.morale = max(0.0, (player.morale or 65.0) - 3.0)
                self.session.flush()
                return f"{name} is not happy but accepts your decision... for now."
            else:
                # Angry
                factors.relationship_with_manager -= 10.0
                player.morale = max(0.0, (player.morale or 65.0) - 12.0)
                self.session.flush()
                return f"{name} storms out of your office. This isn't over."

        elif response == ComplaintResponse.DISCUSS_CONTRACT:
            factors.relationship_with_manager += 5.0
            player.morale = min(100.0, (player.morale or 65.0) + 6.0)
            self.session.flush()
            return f"{name} is glad you're open to negotiations."

        elif response == ComplaintResponse.WILL_REVIEW:
            factors.relationship_with_manager += 2.0
            player.morale = min(100.0, (player.morale or 65.0) + 3.0)
            self.session.flush()
            return f"{name} accepts that you'll look into it."

        self.session.flush()
        return f"{name} acknowledges your response."

    def _check_promises(
        self, club_id: int, season: Season
    ) -> list[PlayerComplaint]:
        """Check if any promises have been broken and generate complaints."""
        global _next_complaint_id
        broken: list[PlayerComplaint] = []
        current_md = season.current_matchday or 0

        for pid, promise in list(_promises.items()):
            player = self.session.query(Player).get(pid)
            if not player or player.club_id != club_id:
                _promises.pop(pid, None)
                continue

            weeks_since = current_md - promise.get("matchday", 0)
            if weeks_since < 5:
                continue  # Give some time

            if promise["type"] == "game_time":
                satisfaction = self.check_playing_time_satisfaction(pid)
                if satisfaction < -5:
                    # Promise broken
                    _promises.pop(pid)
                    factors = _happiness.get(pid, HappinessFactors())
                    factors.relationship_with_manager -= 12.0
                    player.morale = max(0.0, (player.morale or 65.0) - 15.0)

                    complaint = PlayerComplaint(
                        complaint_id=_next_complaint_id,
                        player_id=pid,
                        player_name=player.short_name or player.name,
                        complaint_type=ComplaintType.PLAYING_TIME,
                        message="You promised me game time and didn't deliver. I want out.",
                        severity=0.9,
                        available_responses=[
                            ComplaintResponse.CONSIDER_SELLING,
                            ComplaintResponse.IMPORTANT_MEMBER,
                            ComplaintResponse.GOING_NOWHERE,
                        ],
                    )
                    _complaints[_next_complaint_id] = complaint
                    _next_complaint_id += 1
                    broken.append(complaint)

                    season_obj = self._current_season()
                    self.session.add(NewsItem(
                        season=season_obj.year,
                        matchday=season_obj.current_matchday,
                        headline=f"{player.short_name or player.name} angry over broken promise",
                        body=f"{player.name} feels the manager has broken their promise "
                             f"of more playing time.",
                        category="manager",
                    ))
                else:
                    # Promise kept -- clear it
                    _promises.pop(pid)

        self.session.flush()
        return broken

    def _expected_role(self, player: Player) -> SquadRole:
        """Determine what role a player should expect from ability."""
        squad = self.session.query(Player).filter_by(club_id=player.club_id).all()
        if not squad:
            return SquadRole.FIRST_TEAM

        overalls = sorted((p.overall or 50 for p in squad), reverse=True)
        ovr = player.overall or 50
        rank = sum(1 for v in overalls if v > ovr)

        if rank < 5:
            return SquadRole.KEY_PLAYER
        elif rank < 11:
            return SquadRole.FIRST_TEAM
        elif rank < 18:
            return SquadRole.ROTATION
        elif (player.age or 25) < 21:
            return SquadRole.YOUTH
        else:
            return SquadRole.BACKUP


# ══════════════════════════════════════════════════════════════════════════
#  RelationshipManager
# ══════════════════════════════════════════════════════════════════════════

class RelationshipManager:
    """Manages inter-player relationships, chemistry, cliques, and mentoring."""

    def __init__(self, session: Session):
        self.session = session

    # ── Relationship building ─────────────────────────────────────────────

    def build_relationships(self, club_id: int):
        """Auto-create or update relationships for all players at a club.

        Chemistry bonuses:
        - Same nationality: +15
        - Large age gap (mentor potential): flags mentor relationship
        - New signings start with lower base chemistry
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if len(players) < 2:
            return

        for i, pa in enumerate(players):
            for pb in players[i + 1:]:
                key = _rel_key(pa.id, pb.id)
                if key in _relationships:
                    continue  # already exists

                base_chem = 45.0 + random.uniform(-5, 5)

                # Nationality bonus
                if pa.nationality and pb.nationality and pa.nationality == pb.nationality:
                    base_chem += 15.0

                # Position proximity bonus (same line)
                if _position_line(pa.position) == _position_line(pb.position):
                    base_chem += 5.0

                # Mentor detection
                is_mentor = False
                if pa.age and pb.age:
                    age_diff = abs(pa.age - pb.age)
                    if age_diff >= 8:
                        older = pa if pa.age > pb.age else pb
                        younger = pb if pa.age > pb.age else pa
                        if (older.overall or 50) >= 75 and (younger.age or 25) < 22:
                            is_mentor = True
                            base_chem += 10.0

                rel = Relationship(
                    player_a_id=key[0],
                    player_b_id=key[1],
                    chemistry=max(0.0, min(100.0, base_chem)),
                    is_mentor=is_mentor,
                )
                _relationships[key] = rel

    def process_weekly_chemistry(self, club_id: int):
        """Chemistry grows over time for teammates training together."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        player_ids = {p.id for p in players}

        for key, rel in _relationships.items():
            if key[0] not in player_ids or key[1] not in player_ids:
                continue

            # Natural growth from training together
            growth = random.uniform(0.3, 1.5)

            # Conflicts slow growth
            if rel.is_conflict:
                growth = random.uniform(-0.5, 0.3)

            rel.chemistry = max(0.0, min(100.0, rel.chemistry + growth))

            # Conflict resolution chance
            if rel.is_conflict and random.random() < 0.08:
                rel.is_conflict = False
                rel.chemistry = max(rel.chemistry, 35.0)

    def process_match_day_relationships(
        self, club_id: int, goals_for: int, goals_against: int
    ):
        """After a match, winning together boosts chemistry; losing can strain it."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        player_ids = {p.id for p in players}

        goal_diff = goals_for - goals_against

        for key, rel in _relationships.items():
            if key[0] not in player_ids or key[1] not in player_ids:
                continue

            if goal_diff > 0:
                # Win -- small chemistry boost
                rel.chemistry = min(100.0, rel.chemistry + random.uniform(0.5, 2.0))
            elif goal_diff < 0:
                # Loss -- slight friction
                rel.chemistry = max(0.0, rel.chemistry - random.uniform(0.0, 1.5))
                # Losing streak + low chemistry = conflict risk
                if rel.chemistry < 30 and random.random() < 0.05:
                    rel.is_conflict = True

    def get_dressing_room_mood(self, club_id: int) -> dict:
        """Aggregate dressing room atmosphere.

        Returns dict with spirit, chemistry_avg, conflicts, leaders, newcomers.
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        if not players:
            return {
                "spirit": 50.0, "spirit_label": "Average",
                "chemistry_avg": 50.0, "conflicts": 0,
                "leaders": 0, "cliques": 0, "player_count": 0,
            }

        player_ids = {p.id for p in players}

        # Average morale
        avg_morale = sum((p.morale or 65.0) for p in players) / len(players)

        # Average chemistry
        club_rels = [
            r for k, r in _relationships.items()
            if k[0] in player_ids and k[1] in player_ids
        ]
        avg_chem = (
            sum(r.chemistry for r in club_rels) / len(club_rels)
            if club_rels else 50.0
        )

        conflicts = sum(1 for r in club_rels if r.is_conflict)
        mentors = sum(1 for r in club_rels if r.is_mentor)

        # Leaders: high composure + high age + high overall
        leaders = [
            p for p in players
            if (p.composure or 50) >= 70 and (p.age or 25) >= 26
            and (p.overall or 50) >= 70
        ]

        # Spirit combines morale and chemistry
        spirit = avg_morale * 0.6 + avg_chem * 0.4 - conflicts * 3.0
        spirit = max(0.0, min(100.0, spirit))

        return {
            "spirit": round(spirit, 1),
            "spirit_label": _spirit_label(spirit),
            "chemistry_avg": round(avg_chem, 1),
            "morale_avg": round(avg_morale, 1),
            "conflicts": conflicts,
            "mentorships": mentors,
            "leaders": len(leaders),
            "leader_names": [p.short_name or p.name for p in leaders[:5]],
            "cliques": len(self.get_squad_cliques(club_id)),
            "player_count": len(players),
        }

    def get_squad_leaders(self, club_id: int) -> list[dict]:
        """Identify natural squad leaders."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        leaders = []
        for p in players:
            leadership_score = (
                (p.composure or 50) * 0.3 +
                (p.overall or 50) * 0.25 +
                (p.age or 25) * 1.0 +
                (p.big_match or 65) * 0.15 +
                (p.morale or 65) * 0.1
            )
            leaders.append({
                "id": p.id,
                "name": p.short_name or p.name,
                "leadership_score": round(leadership_score, 1),
                "composure": p.composure,
                "age": p.age,
                "overall": p.overall,
            })
        leaders.sort(key=lambda x: x["leadership_score"], reverse=True)
        return leaders[:10]

    def get_squad_cliques(self, club_id: int) -> list[list[dict]]:
        """Detect cliques: groups of 3+ players with same nationality.

        Cliques are neutral-to-positive unless morale is low, in which case
        they can become divisive.
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        nationality_groups: dict[str, list[Player]] = {}

        for p in players:
            nat = p.nationality or "Unknown"
            nationality_groups.setdefault(nat, []).append(p)

        cliques = []
        for nat, group in nationality_groups.items():
            if len(group) >= 3:
                clique = [
                    {"id": p.id, "name": p.short_name or p.name,
                     "nationality": nat, "overall": p.overall}
                    for p in group
                ]
                cliques.append(clique)

        return cliques

    def process_player_conflict(self, player_a_id: int, player_b_id: int) -> str:
        """Trigger a conflict between two players. Returns description."""
        key = _rel_key(player_a_id, player_b_id)
        rel = _relationships.get(key)

        pa = self.session.query(Player).get(player_a_id)
        pb = self.session.query(Player).get(player_b_id)
        if not pa or not pb:
            return "Players not found."

        if rel is None:
            rel = Relationship(
                player_a_id=key[0], player_b_id=key[1],
                chemistry=25.0, is_conflict=True,
            )
            _relationships[key] = rel
        else:
            rel.is_conflict = True
            rel.chemistry = max(0.0, rel.chemistry - 20.0)

        # Morale hit for both
        pa.morale = max(0.0, (pa.morale or 65.0) - random.uniform(5, 12))
        pb.morale = max(0.0, (pb.morale or 65.0) - random.uniform(5, 12))

        season = self.session.query(Season).order_by(Season.year.desc()).first()
        if season:
            self.session.add(NewsItem(
                season=season.year,
                matchday=season.current_matchday,
                headline=f"Rift between {pa.short_name or pa.name} and "
                         f"{pb.short_name or pb.name}",
                body=f"Reports suggest a falling out between "
                     f"{pa.name} and {pb.name} in the dressing room.",
                category="general",
            ))

        self.session.flush()
        name_a = pa.short_name or pa.name
        name_b = pb.short_name or pb.name
        return f"A conflict has erupted between {name_a} and {name_b}."

    def get_chemistry_between(self, player_a_id: int, player_b_id: int) -> float:
        """Return the chemistry value between two players."""
        key = _rel_key(player_a_id, player_b_id)
        rel = _relationships.get(key)
        return rel.chemistry if rel else 50.0

    def get_mentor_pairs(self, club_id: int) -> list[dict]:
        """Return active mentor-protege pairs."""
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        player_map = {p.id: p for p in players}
        player_ids = set(player_map.keys())
        pairs = []

        for key, rel in _relationships.items():
            if not rel.is_mentor:
                continue
            if key[0] not in player_ids or key[1] not in player_ids:
                continue

            pa = player_map[key[0]]
            pb = player_map[key[1]]
            mentor = pa if (pa.age or 25) > (pb.age or 25) else pb
            protege = pb if mentor is pa else pa

            pairs.append({
                "mentor_id": mentor.id,
                "mentor_name": mentor.short_name or mentor.name,
                "protege_id": protege.id,
                "protege_name": protege.short_name or protege.name,
                "chemistry": rel.chemistry,
            })

        return pairs


# ══════════════════════════════════════════════════════════════════════════
#  Module-level helpers
# ══════════════════════════════════════════════════════════════════════════

def _rel_key(a: int, b: int) -> tuple[int, int]:
    """Canonical sorted key for a pair of player IDs."""
    return (min(a, b), max(a, b))


def _role_to_expectation(role: SquadRole) -> PlayingTimeExpectation:
    return {
        SquadRole.KEY_PLAYER: PlayingTimeExpectation.REGULAR_STARTER,
        SquadRole.FIRST_TEAM: PlayingTimeExpectation.REGULAR_STARTER,
        SquadRole.ROTATION: PlayingTimeExpectation.SQUAD_ROTATION,
        SquadRole.BACKUP: PlayingTimeExpectation.BACKUP,
        SquadRole.YOUTH: PlayingTimeExpectation.YOUTH_PROSPECT,
        SquadRole.NOT_NEEDED: PlayingTimeExpectation.BACKUP,
    }[role]


def _role_label(role: SquadRole) -> str:
    return {
        SquadRole.KEY_PLAYER: "Key Player",
        SquadRole.FIRST_TEAM: "First Team Regular",
        SquadRole.ROTATION: "Rotation Option",
        SquadRole.BACKUP: "Backup",
        SquadRole.YOUTH: "Youth Prospect",
        SquadRole.NOT_NEEDED: "Surplus to Requirements",
    }[role]


def _role_rank(role: SquadRole) -> int:
    """Numeric rank for role comparison (higher = more prestigious)."""
    return {
        SquadRole.NOT_NEEDED: 0,
        SquadRole.YOUTH: 1,
        SquadRole.BACKUP: 2,
        SquadRole.ROTATION: 3,
        SquadRole.FIRST_TEAM: 4,
        SquadRole.KEY_PLAYER: 5,
    }[role]


def _position_line(pos: str | None) -> str:
    """Map position to broad line for chemistry grouping."""
    if not pos:
        return "mid"
    pos = pos.upper()
    if pos == "GK":
        return "gk"
    if pos in ("CB", "LB", "RB", "LWB", "RWB"):
        return "def"
    if pos in ("CDM", "CM", "CAM", "LM", "RM"):
        return "mid"
    return "att"


def _spirit_label(spirit: float) -> str:
    if spirit >= 85:
        return "Excellent"
    elif spirit >= 70:
        return "Good"
    elif spirit >= 55:
        return "Steady"
    elif spirit >= 40:
        return "Fragile"
    elif spirit >= 25:
        return "Poor"
    return "Toxic"
