"""Core consequence processor — translates game events into cascading effects."""
from __future__ import annotations

import random

from sqlalchemy import or_
from sqlalchemy.orm import Session

from fm.core.event_bus import (
    CAPTAIN_INJURED,
    EventBus,
    FINANCIAL_OVERSPEND,
    MATCH_RESULT,
    MATCH_STATS,
    OVERTRAINING,
    PLAYER_DROPPED,
    PLAYER_SOLD,
    PROMISE_BROKEN,
    YOUTH_PLAYED,
)
from fm.db.models import (
    BoardExpectation,
    Club,
    ConsequenceLog,
    Player,
    PlayerRelationship,
    Promise,
)
from fm.utils.helpers import clamp


class ConsequenceEngine:
    """Processes game events and applies cascading consequences to the DB."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ── Public API ────────────────────────────────────────────────────────

    def register_handlers(self, bus: EventBus) -> None:
        """Wire every consequence handler onto *bus*."""
        bus.subscribe(PLAYER_DROPPED, self._handle_player_dropped)
        bus.subscribe(PLAYER_SOLD, self._handle_player_sold)
        bus.subscribe(PROMISE_BROKEN, self._handle_promise_broken)
        bus.subscribe(OVERTRAINING, self._handle_overtraining)
        bus.subscribe(YOUTH_PLAYED, self._handle_youth_played)
        bus.subscribe(FINANCIAL_OVERSPEND, self._handle_financial_overspend)
        bus.subscribe(CAPTAIN_INJURED, self._handle_captain_injured)
        bus.subscribe(MATCH_RESULT, self._handle_match_result)
        bus.subscribe(MATCH_STATS, self._handle_poor_performance)

    # ── Handlers ──────────────────────────────────────────────────────────

    def _handle_player_dropped(self, _event_type: str, **data) -> None:
        """A player was left out of the matchday squad.

        Expected *data*: player_id, club_id, matchday, season.
        """
        player_id: int = data["player_id"]
        club_id: int = data["club_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]

        player: Player | None = self._session.get(Player, player_id)
        if player is None:
            return

        player.consecutive_benched += 1

        if player.consecutive_benched >= 3:
            player.happiness = clamp(player.happiness - 10, 0.0, 100.0)
            player.trust_in_manager = clamp(player.trust_in_manager - 5, 0.0, 100.0)

            # Friends suffer a morale dip
            friends = self._find_friends(player_id)
            for friend in friends:
                friend.morale = clamp(friend.morale - random.randint(3, 8), 0.0, 100.0)

            # Leaders drag down team spirit
            if player.leadership >= 70:
                club: Club | None = self._session.get(Club, club_id)
                if club is not None:
                    club.team_spirit = clamp(club.team_spirit - 5, 0.0, 100.0)

            self._log(
                season, matchday,
                trigger=PLAYER_DROPPED,
                target_type="player",
                target_id=player_id,
                effect=f"{player.name} unhappy after {player.consecutive_benched} games benched",
                magnitude=-10.0,
            )

    def _handle_player_sold(self, _event_type: str, **data) -> None:
        """A player was sold to another club.

        Expected *data*: player_id, club_id, buyer_club_id, matchday, season.
        """
        player_id: int = data["player_id"]
        club_id: int = data["club_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]

        player: Player | None = self._session.get(Player, player_id)
        if player is None:
            return

        # Friends left behind lose morale
        friends = self._find_friends(player_id, club_id=club_id)
        for friend in friends:
            friend.morale = clamp(friend.morale - random.randint(5, 15), 0.0, 100.0)

        # Selling a fan favourite upsets the fans
        if player.fan_favorite:
            board: BoardExpectation | None = (
                self._session.query(BoardExpectation)
                .filter_by(club_id=club_id)
                .first()
            )
            if board is not None:
                board.fan_happiness = clamp(board.fan_happiness - 10, 0.0, 100.0)

        self._log(
            season, matchday,
            trigger=PLAYER_SOLD,
            target_type="club",
            target_id=club_id,
            effect=f"{player.name} sold — friends upset, fan reaction processed",
            magnitude=-10.0,
        )

    def _handle_promise_broken(self, _event_type: str, **data) -> None:
        """A promise to a player was broken.

        Expected *data*: promise_id, player_id, club_id, matchday, season.
        """
        promise_id: int = data["promise_id"]
        player_id: int = data["player_id"]
        club_id: int = data["club_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]

        player: Player | None = self._session.get(Player, player_id)
        promise: Promise | None = self._session.get(Promise, promise_id)
        if player is None:
            return

        player.happiness = clamp(player.happiness - 25, 0.0, 100.0)
        player.trust_in_manager = clamp(player.trust_in_manager - 20, 0.0, 100.0)

        if player.happiness < 30:
            player.wants_transfer = True

        if promise is not None:
            promise.broken = True

        self._log(
            season, matchday,
            trigger=PROMISE_BROKEN,
            target_type="player",
            target_id=player_id,
            effect=f"Broken promise to {player.name} — happiness {player.happiness:.0f}, trust {player.trust_in_manager:.0f}",
            magnitude=-25.0,
        )

    def _handle_overtraining(self, _event_type: str, **data) -> None:
        """Player was over-trained, raising injury risk.

        Expected *data*: player_id, club_id, matchday, season.
        """
        player_id: int = data["player_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]

        player: Player | None = self._session.get(Player, player_id)
        if player is None:
            return

        # Temporary proneness boost (+20), tracked via ConsequenceLog so the
        # caller can revert it after 4 matchdays.
        player.injury_proneness = min(player.injury_proneness + 20, 99)

        self._log(
            season, matchday,
            trigger=OVERTRAINING,
            target_type="player",
            target_id=player_id,
            effect=f"{player.name} overtrained — injury_proneness +20 for 4 weeks",
            magnitude=20.0,
        )

    def _handle_youth_played(self, _event_type: str, **data) -> None:
        """A youth player was given match time.

        Expected *data*: player_id, club_id, matchday, season.
        """
        player_id: int = data["player_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]

        player: Player | None = self._session.get(Player, player_id)
        if player is None:
            return

        # Under-21 players gain a small potential nudge (capped at 99)
        if player.age <= 21 and player.potential < 99:
            player.potential = min(player.potential + 1, 99)

            self._log(
                season, matchday,
                trigger=YOUTH_PLAYED,
                target_type="player",
                target_id=player_id,
                effect=f"{player.name} (age {player.age}) gained +1 potential from match experience",
                magnitude=1.0,
            )

    def _handle_financial_overspend(self, _event_type: str, **data) -> None:
        """Club is spending beyond its budget.

        Expected *data*: club_id, matchday, season, consecutive_matchdays.
        """
        club_id: int = data["club_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]
        consecutive: int = data["consecutive_matchdays"]

        board: BoardExpectation | None = (
            self._session.query(BoardExpectation)
            .filter_by(club_id=club_id)
            .first()
        )
        if board is None:
            return

        board.board_confidence = clamp(board.board_confidence - 5, 0.0, 100.0)

        if consecutive >= 3:
            board.transfer_embargo = True

        if consecutive >= 6:
            board.ultimatum_active = True

        self._log(
            season, matchday,
            trigger=FINANCIAL_OVERSPEND,
            target_type="board",
            target_id=club_id,
            effect=f"Financial overspend ({consecutive} matchdays) — confidence {board.board_confidence:.0f}",
            magnitude=-5.0 * min(consecutive, 6),
        )

    def _handle_captain_injured(self, _event_type: str, **data) -> None:
        """The club captain was injured.

        Expected *data*: player_id, club_id, matchday, season.
        """
        player_id: int = data["player_id"]
        club_id: int = data["club_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]

        club: Club | None = self._session.get(Club, club_id)
        if club is None:
            return

        club.team_spirit = clamp(club.team_spirit - 8, 0.0, 100.0)

        # All squad members lose a little morale
        squad = (
            self._session.query(Player)
            .filter(Player.club_id == club_id, Player.id != player_id)
            .all()
        )
        for mate in squad:
            mate.morale = clamp(mate.morale - 3, 0.0, 100.0)

        player: Player | None = self._session.get(Player, player_id)
        name = player.name if player else f"Player#{player_id}"

        self._log(
            season, matchday,
            trigger=CAPTAIN_INJURED,
            target_type="club",
            target_id=club_id,
            effect=f"Captain {name} injured — team spirit -{8}, squad morale hit",
            magnitude=-8.0,
        )

    def _handle_match_result(self, _event_type: str, **data) -> None:
        """A match finished — adjust board confidence.

        Expected *data*: club_id, home_goals, away_goals, is_home,
                         expected_result, matchday, season.

        *expected_result* should be one of ``"win"``, ``"draw"``, ``"loss"``.
        """
        club_id: int = data["club_id"]
        home_goals: int = data["home_goals"]
        away_goals: int = data["away_goals"]
        is_home: bool = data["is_home"]
        expected: str = data.get("expected_result", "draw")
        matchday: int = data["matchday"]
        season: int = data["season"]

        board: BoardExpectation | None = (
            self._session.query(BoardExpectation)
            .filter_by(club_id=club_id)
            .first()
        )
        if board is None:
            return

        # Determine actual result from the club's perspective
        if is_home:
            my_goals, their_goals = home_goals, away_goals
        else:
            my_goals, their_goals = away_goals, home_goals

        if my_goals > their_goals:
            actual = "win"
        elif my_goals < their_goals:
            actual = "loss"
        else:
            actual = "draw"

        # Map result to numeric value for gap calculation
        _result_value = {"win": 3, "draw": 1, "loss": 0}
        result_gap = _result_value[actual] - _result_value[expected]

        # Scale: meeting expectations = small positive, exceeding = bigger, failing = negative
        if result_gap > 0:
            delta = random.randint(4, 8)   # better than expected
        elif result_gap == 0:
            delta = random.randint(1, 3)   # met expectations
        elif result_gap == -1:
            delta = random.randint(-5, -2)  # slightly worse
        else:
            delta = random.randint(-8, -4)  # much worse (e.g., expected win, got loss)

        board.board_confidence = clamp(board.board_confidence + delta, 0.0, 100.0)

        self._log(
            season, matchday,
            trigger=MATCH_RESULT,
            target_type="board",
            target_id=club_id,
            effect=f"Result {actual} (expected {expected}) — confidence {'+' if delta >= 0 else ''}{delta}",
            magnitude=float(delta),
        )

    def _handle_poor_performance(self, _event_type: str, **data) -> None:
        """Process individual and team stat-based consequences after a match.

        Expected *data*:
            club_id, matchday, season,
            players: list of dicts with keys:
                player_id, rating, fouls, big_chances_missed, saves, is_gk,
                position
            possession_pct: float (team's possession percentage),
            shots_on_target: int (team's total shots on target),
            won: bool (did the team win?),
        """
        club_id: int = data["club_id"]
        matchday: int = data["matchday"]
        season: int = data["season"]
        players_data: list[dict] = data.get("players", [])
        possession_pct: float = data.get("possession_pct", 50.0)
        sot: int = data.get("shots_on_target", 5)
        won: bool = data.get("won", False)

        for pdata in players_data:
            player: Player | None = self._session.get(Player, pdata["player_id"])
            if player is None:
                continue

            rating = pdata.get("rating", 6.0)
            fouls = pdata.get("fouls", 0)
            big_missed = pdata.get("big_chances_missed", 0)
            saves = pdata.get("saves", 0)
            is_gk = pdata.get("is_gk", False)
            position = pdata.get("position", "")

            # Poor performance: extra form reduction
            if rating < 5.5:
                form_penalty = (5.5 - rating) * 3.0  # 1.5 to ~9 pts
                player.morale = clamp(player.morale - form_penalty, 0.0, 100.0)
                self._log(
                    season, matchday,
                    trigger=MATCH_STATS,
                    target_type="player",
                    target_id=player.id,
                    effect=f"{player.name} poor rating {rating:.1f} — morale -{form_penalty:.1f}",
                    magnitude=-form_penalty,
                )

            # Frequent fouling: discipline issue
            if fouls >= 3:
                player.temperament = max(
                    (player.temperament or 50) - 2, 1,
                )
                self._log(
                    season, matchday,
                    trigger=MATCH_STATS,
                    target_type="player",
                    target_id=player.id,
                    effect=f"{player.name} committed {fouls} fouls — temperament -2",
                    magnitude=-2.0,
                )

            # Missed big chances: composure hit
            if big_missed >= 2:
                player.morale = clamp(player.morale - 4.0, 0.0, 100.0)
                self._log(
                    season, matchday,
                    trigger=MATCH_STATS,
                    target_type="player",
                    target_id=player.id,
                    effect=f"{player.name} missed {big_missed} big chances — morale -4",
                    magnitude=-4.0,
                )

            # Heroic GK performance
            if is_gk and saves >= 5:
                player.morale = clamp(player.morale + 8.0, 0.0, 100.0)
                self._log(
                    season, matchday,
                    trigger=MATCH_STATS,
                    target_type="player",
                    target_id=player.id,
                    effect=f"{player.name} heroic {saves} saves — morale +8",
                    magnitude=8.0,
                )

        # --- Team-wide stat-based consequences ---

        # Low possession: team was dominated
        if possession_pct < 40.0:
            squad = (
                self._session.query(Player)
                .filter(Player.club_id == club_id)
                .all()
            )
            for p in squad:
                p.morale = clamp(p.morale - 2.0, 0.0, 100.0)
            self._log(
                season, matchday,
                trigger=MATCH_STATS,
                target_type="club",
                target_id=club_id,
                effect=f"Low possession ({possession_pct:.1f}%) — squad morale -2",
                magnitude=-2.0,
            )

        # Zero shots on target: attackers demoralized
        if sot == 0:
            attackers = (
                self._session.query(Player)
                .filter(
                    Player.club_id == club_id,
                    Player.position.in_(["ST", "CF", "LW", "RW", "CAM"]),
                )
                .all()
            )
            for p in attackers:
                p.morale = clamp(p.morale - 5.0, 0.0, 100.0)
            self._log(
                season, matchday,
                trigger=MATCH_STATS,
                target_type="club",
                target_id=club_id,
                effect="Zero shots on target — attackers morale -5",
                magnitude=-5.0,
            )

        # Counter-attacking win: won with < 30% possession
        if won and possession_pct < 30.0:
            squad = (
                self._session.query(Player)
                .filter(Player.club_id == club_id)
                .all()
            )
            for p in squad:
                p.morale = clamp(p.morale + 5.0, 0.0, 100.0)
            self._log(
                season, matchday,
                trigger=MATCH_STATS,
                target_type="club",
                target_id=club_id,
                effect=f"Counter-attacking win ({possession_pct:.1f}% poss) — squad morale +5",
                magnitude=5.0,
            )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _find_friends(
        self, player_id: int, *, club_id: int | None = None,
    ) -> list[Player]:
        """Return *Player* objects who are friends with *player_id*.

        If *club_id* is given, only return friends on that club.
        """
        rels = (
            self._session.query(PlayerRelationship)
            .filter(
                PlayerRelationship.relationship_type.in_(("friends", "close_friends")),
                or_(
                    PlayerRelationship.player_a_id == player_id,
                    PlayerRelationship.player_b_id == player_id,
                ),
            )
            .all()
        )
        friend_ids: list[int] = []
        for rel in rels:
            fid = rel.player_b_id if rel.player_a_id == player_id else rel.player_a_id
            friend_ids.append(fid)

        if not friend_ids:
            return []

        query = self._session.query(Player).filter(Player.id.in_(friend_ids))
        if club_id is not None:
            query = query.filter(Player.club_id == club_id)
        return query.all()

    def _log(
        self,
        season: int,
        matchday: int,
        trigger: str,
        target_type: str,
        target_id: int,
        effect: str,
        magnitude: float,
    ) -> None:
        """Create a :class:`ConsequenceLog` entry."""
        entry = ConsequenceLog(
            season=season,
            matchday=matchday,
            trigger_event=trigger,
            target_type=target_type,
            target_id=target_id,
            effect=effect,
            magnitude=magnitude,
        )
        self._session.add(entry)
