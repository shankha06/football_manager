"""Real-life football situations, background stories, and their impacts.

Every situation here happens in real football. Each creates short-term and
long-term consequences that ripple through morale, form, finances, and narratives.
"""
from __future__ import annotations

import random

from sqlalchemy.orm import Session

from fm.db.models import (
    Player, Club, Fixture, LeagueStanding, BoardExpectation,
    PlayerRelationship, NewsItem, Season, Injury, Manager,
    ConsequenceLog, MatchEvent,
)
from fm.utils.helpers import clamp


# ── Helper ──────────────────────────────────────────────────────────────────


def _log(
    session: Session,
    season: int,
    matchday: int,
    trigger: str,
    target_type: str,
    target_id: int,
    effect: str,
    magnitude: float,
) -> None:
    """Create a :class:`ConsequenceLog` entry."""
    session.add(ConsequenceLog(
        season=season,
        matchday=matchday,
        trigger_event=trigger,
        target_type=target_type,
        target_id=target_id,
        effect=effect,
        magnitude=magnitude,
    ))


# ── System 1: Derby & Rivalry Matches ──────────────────────────────────────


class DerbyRivalry:
    """Derby matches have higher intensity, more cards, more drama."""

    RIVALRIES = [
        ("Manchester United", "Manchester City"),
        ("Manchester United", "Liverpool"),
        ("Liverpool", "Everton"),
        ("Arsenal", "Tottenham"),
        ("Barcelona", "Real Madrid"),
        ("AC Milan", "Inter"),
        ("Juventus", "Inter"),
        ("Borussia Dortmund", "Bayern"),
        ("Paris Saint Germain", "Marseille"),
        ("Roma", "Lazio"),
        ("Celtic", "Rangers"),
        ("Fenerbahce", "Galatasaray"),
        ("Porto", "Benfica"),
        ("Ajax", "Feyenoord"),
        ("Atletico Madrid", "Real Madrid"),
    ]

    @staticmethod
    def is_derby(home_club_name: str, away_club_name: str) -> bool:
        """Check if fixture is a derby."""
        h = (home_club_name or "").lower()
        a = (away_club_name or "").lower()
        for name_a, name_b in DerbyRivalry.RIVALRIES:
            la, lb = name_a.lower(), name_b.lower()
            if (la in h and lb in a) or (lb in h and la in a):
                return True
        return False

    @staticmethod
    def apply_derby_effects(
        session: Session, fixture_id: int,
        home_club_id: int, away_club_id: int,
        season: int, matchday: int,
    ) -> list[str]:
        """Apply pre-match derby effects. Returns effect descriptions."""
        effects: list[str] = []
        home_club = session.get(Club, home_club_id)
        away_club = session.get(Club, away_club_id)
        if not home_club or not away_club:
            return effects

        if not DerbyRivalry.is_derby(home_club.name, away_club.name):
            return effects

        # Both teams: morale +3 (extra motivation)
        for cid in (home_club_id, away_club_id):
            squad = session.query(Player).filter_by(club_id=cid).all()
            for p in squad:
                p.morale = clamp(p.morale + 3, 0.0, 100.0)
                p.aggression = min(99, (p.aggression or 50) + 5)

        # Attendance boost +10%
        fixture = session.get(Fixture, fixture_id)
        if fixture and home_club.stadium_capacity:
            base_attendance = int(home_club.stadium_capacity * 0.85)
            fixture.attendance = min(
                home_club.stadium_capacity,
                int(base_attendance * 1.10),
            )

        # News
        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"Derby day: {home_club.name} vs {away_club.name}",
            body=f"The city holds its breath as {home_club.name} prepare to "
                 f"host rivals {away_club.name} in a fierce derby.",
            category="match",
        ))
        effects.append(
            f"Derby: {home_club.name} vs {away_club.name} — morale +3, aggression +5"
        )

        _log(session, season, matchday, "derby_pre_match", "club",
             home_club_id, "; ".join(effects), 3.0)
        return effects

    @staticmethod
    def apply_derby_result(
        session: Session, club_id: int, opponent_id: int,
        won: bool, goal_diff: int,
        season: int, matchday: int,
    ) -> list[str]:
        """Post-derby consequences."""
        effects: list[str] = []
        club = session.get(Club, club_id)
        if not club:
            return effects

        squad = session.query(Player).filter_by(club_id=club_id).all()
        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()

        if won:
            # Winner: team_spirit +5, fan_happiness +5
            club.team_spirit = clamp(club.team_spirit + 5, 0.0, 100.0)
            if board:
                board.fan_happiness = clamp(board.fan_happiness + 5, 0.0, 100.0)
            for p in squad:
                p.morale = clamp(p.morale + 3, 0.0, 100.0)
            effects.append(f"{club.name}: Derby win — spirit +5, fan happiness +5, morale +3")
        else:
            # Loser: team_spirit -5, fan_happiness -5
            club.team_spirit = clamp(club.team_spirit - 5, 0.0, 100.0)
            if board:
                board.fan_happiness = clamp(board.fan_happiness - 5, 0.0, 100.0)
            for p in squad:
                p.morale = clamp(p.morale - 3, 0.0, 100.0)
            effects.append(f"{club.name}: Derby loss — spirit -5, fan happiness -5, morale -3")

            # Lost by 3+: humiliation
            if goal_diff <= -3:
                if board:
                    board.fan_happiness = clamp(board.fan_happiness - 10, 0.0, 100.0)
                for p in squad:
                    p.morale = clamp(p.morale - 5, 0.0, 100.0)
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"Humiliation for {club.name} in derby",
                    body=f"{club.name} were embarrassed by their rivals, "
                         f"losing by {abs(goal_diff)} goals in the derby.",
                    category="match",
                ))
                effects.append(f"{club.name}: Derby humiliation — extra fan_happiness -10, morale -5")

        _log(session, season, matchday, "derby_result", "club", club_id,
             "; ".join(effects), 5.0 if won else -5.0)
        return effects


# ── System 2: New Signing Integration ──────────────────────────────────────


class NewSigningIntegration:
    """New signings need time to adapt to the team."""

    @staticmethod
    def process_new_signing(
        session: Session, player_id: int, club_id: int,
        season: int, matchday: int,
    ) -> list[str]:
        """Called when a player joins a new club."""
        effects: list[str] = []
        player = session.get(Player, player_id)
        if not player:
            return effects

        # Set initial adaptation state
        player.tactical_familiarity = 30.0
        player.team_chemistry = 25.0
        player.morale = clamp((player.morale or 65.0) + 10, 0.0, 100.0)

        club = session.get(Club, club_id)
        club_players = session.query(Player).filter(
            Player.club_id == club_id, Player.id != player_id
        ).all()

        # Check nationality difference
        if club_players:
            nationalities = [p.nationality for p in club_players if p.nationality]
            if nationalities:
                from collections import Counter
                majority_nat = Counter(nationalities).most_common(1)[0][0]
                if player.nationality and player.nationality != majority_nat:
                    player.team_chemistry = clamp(player.team_chemistry - 5, 0.0, 100.0)
                    effects.append(
                        f"{player.name}: Different nationality — chemistry -5"
                    )

        # Check if player knows someone (PlayerRelationship)
        from sqlalchemy import or_
        rels = session.query(PlayerRelationship).filter(
            PlayerRelationship.relationship_type.in_(("friends", "close_friends")),
            or_(
                PlayerRelationship.player_a_id == player_id,
                PlayerRelationship.player_b_id == player_id,
            ),
        ).all()
        friend_ids = set()
        for rel in rels:
            fid = rel.player_b_id if rel.player_a_id == player_id else rel.player_a_id
            friend_ids.add(fid)
        club_friend_ids = {p.id for p in club_players} & friend_ids
        if club_friend_ids:
            player.team_chemistry = clamp(player.team_chemistry + 15, 0.0, 100.0)
            effects.append(f"{player.name}: Knows teammate(s) — chemistry +15")

        effects.append(
            f"{player.name}: New signing — familiarity 30, chemistry "
            f"{player.team_chemistry:.0f}, morale +10"
        )

        _log(session, season, matchday, "new_signing", "player", player_id,
             "; ".join(effects), 10.0)
        return effects

    @staticmethod
    def process_weekly_integration(
        session: Session, club_id: int,
        season: int, matchday: int,
    ) -> list[str]:
        """Run weekly — improve chemistry for new signings."""
        effects: list[str] = []
        players = session.query(Player).filter(
            Player.club_id == club_id,
            Player.tactical_familiarity < 80,
        ).all()

        for p in players:
            adapt = p.adaptability or 50
            age = p.age or 25
            teamwork = p.teamwork or 50

            fam_gain = 5.0 + adapt / 20.0
            chem_gain = 3.0 + teamwork / 30.0

            # Age modifiers
            if age < 22:
                fam_gain *= 1.3
                chem_gain *= 1.3
            elif age > 30:
                fam_gain *= 0.8
                chem_gain *= 0.8

            # Played in match this week: bonus +5
            if (p.minutes_season or 0) > 0:
                fam_gain += 5.0
                chem_gain += 5.0

            p.tactical_familiarity = clamp(
                (p.tactical_familiarity or 50) + fam_gain, 0.0, 100.0
            )
            p.team_chemistry = clamp(
                (p.team_chemistry or 50) + chem_gain, 0.0, 100.0
            )
            effects.append(
                f"{p.name}: Integration — familiarity +{fam_gain:.1f}, "
                f"chemistry +{chem_gain:.1f}"
            )

        return effects


# ── System 3: Player Milestones & Records ──────────────────────────────────


class PlayerMilestones:
    """Track and reward player achievements."""

    @staticmethod
    def check_milestones(
        session: Session, player_id: int, club_id: int,
        goals_in_match: int, assists_in_match: int,
        clean_sheet: bool, season: int, matchday: int,
    ) -> list[str]:
        """Check if player hit any milestones after a match."""
        effects: list[str] = []
        player = session.get(Player, player_id)
        if not player:
            return effects

        club = session.get(Club, club_id)
        club_name = club.name if club else f"Club#{club_id}"

        # Hat trick (3 goals in a match)
        if goals_in_match >= 3:
            player.morale = clamp(player.morale + 10, 0.0, 100.0)
            player.form = clamp(player.form + 5, 0.0, 100.0)
            # Boost team morale +3
            squad = session.query(Player).filter(
                Player.club_id == club_id, Player.id != player_id
            ).all()
            for p in squad:
                p.morale = clamp(p.morale + 3, 0.0, 100.0)
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"{player.short_name or player.name} scores hat-trick!",
                body=f"{player.name} netted three times for {club_name} "
                     f"in a stunning individual display.",
                category="match",
            ))
            effects.append(f"{player.name}: Hat-trick — morale +10, form +5, team morale +3")

        # First senior goal (young player)
        if goals_in_match > 0 and (player.goals_season or 0) <= goals_in_match:
            if (player.age or 30) <= 21 and (player.goals_season or 0) == goals_in_match:
                player.morale = clamp(player.morale + 15, 0.0, 100.0)
                player.form = clamp(player.form + 10, 0.0, 100.0)
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"{player.short_name or player.name} opens his account for {club_name}!",
                    body=f"Young {player.name} scored his first senior goal for {club_name}.",
                    category="match",
                ))
                effects.append(f"{player.name}: First senior goal — morale +15, form +10")

        # Season goal milestones (10/20/30)
        goals = player.goals_season or 0
        for milestone in (10, 20, 30):
            prev_goals = goals - goals_in_match
            if prev_goals < milestone <= goals:
                player.morale = clamp(player.morale + 5, 0.0, 100.0)
                board = session.query(BoardExpectation).filter_by(club_id=club_id).first()
                if board:
                    board.fan_happiness = clamp(board.fan_happiness + 2, 0.0, 100.0)
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"{player.short_name or player.name} reaches {milestone} goals for the season",
                    body=f"{player.name} has now scored {milestone} goals this season for {club_name}.",
                    category="match",
                ))
                effects.append(f"{player.name}: {milestone} season goals — morale +5")

        # Clean sheet for GK
        if clean_sheet and player.position == "GK":
            player.morale = clamp(player.morale + 3, 0.0, 100.0)
            player.form = clamp(player.form + 2, 0.0, 100.0)
            effects.append(f"{player.name}: Clean sheet — morale +3, form +2")

        # Assist milestones (10/20)
        assists = player.assists_season or 0
        for milestone in (10, 20):
            prev_assists = assists - assists_in_match
            if prev_assists < milestone <= assists:
                player.morale = clamp(player.morale + 3, 0.0, 100.0)
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"{player.short_name or player.name} reaches {milestone} assists",
                    body=f"{player.name} notched his {milestone}th assist of the season.",
                    category="match",
                ))
                effects.append(f"{player.name}: {milestone} season assists — morale +3")

        if effects:
            _log(session, season, matchday, "player_milestone", "player",
                 player_id, "; ".join(effects), float(goals_in_match * 5))

        return effects


# ── System 4: Substitution Psychology ──────────────────────────────────────


class SubstitutionPsychology:
    """Being substituted affects player morale differently based on context."""

    @staticmethod
    def process_substitution(
        session: Session, player_off_id: int, player_on_id: int,
        minute: int, match_score_diff: int, is_tactical: bool,
        player_off_scored: bool,
        season: int, matchday: int,
    ) -> list[str]:
        """Process psychological impact of a substitution."""
        effects: list[str] = []
        player_off = session.get(Player, player_off_id)
        player_on = session.get(Player, player_on_id)
        if not player_off or not player_on:
            return effects

        # Subbed before 45 min (humiliation sub)
        if minute < 45:
            player_off.morale = clamp(player_off.morale - 10, 0.0, 100.0)
            player_off.trust_in_manager = clamp(
                (player_off.trust_in_manager or 60) - 8, 0.0, 100.0
            )
            effects.append(f"{player_off.name}: Subbed before half-time — morale -10, trust -8")

            # Low temperament: refuse handshake
            if (player_off.temperament or 50) < 40:
                club = session.get(Club, player_off.club_id)
                if club:
                    club.team_spirit = clamp(club.team_spirit - 3, 0.0, 100.0)
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"{player_off.short_name or player_off.name} refuses handshake after early sub",
                    body=f"{player_off.name} stormed past the bench after being "
                         f"substituted before half-time.",
                    category="match",
                ))
                effects.append(f"{player_off.name}: Refused handshake — team_spirit -3")

        # Subbed at 60-70 (tactical, normal)
        elif 60 <= minute <= 70:
            player_off.morale = clamp(player_off.morale - 2, 0.0, 100.0)
            player_on.morale = clamp(player_on.morale + 3, 0.0, 100.0)
            effects.append(f"{player_off.name}: Tactical sub — morale -2")

        # Subbed at 80+ while winning (rest/protection)
        elif minute >= 80 and match_score_diff > 0:
            player_off.morale = clamp(player_off.morale + 2, 0.0, 100.0)
            player_on.morale = clamp(player_on.morale + 2, 0.0, 100.0)
            effects.append(f"{player_off.name}: Rest sub while winning — morale +2")

        # Subbed despite scoring
        if player_off_scored and minute < 80:
            player_off.morale = clamp(player_off.morale - 8, 0.0, 100.0)
            player_off.trust_in_manager = clamp(
                (player_off.trust_in_manager or 60) - 5, 0.0, 100.0
            )
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"{player_off.short_name or player_off.name} frustrated after being replaced",
                body=f"{player_off.name} was visibly frustrated after being "
                     f"substituted despite scoring in the match.",
                category="match",
            ))
            effects.append(f"{player_off.name}: Subbed despite scoring — morale -8, trust -5")

        # Star player subbed for youth
        if (player_off.overall or 0) >= 80 and (player_on.age or 30) <= 21:
            player_off.morale = clamp(player_off.morale - 5, 0.0, 100.0)
            player_on.form = clamp((player_on.form or 65) + 5, 0.0, 100.0)
            effects.append(
                f"{player_off.name}: Replaced by youth ({player_on.name}) — morale -5; "
                f"{player_on.name}: confidence +5"
            )

        if effects:
            _log(session, season, matchday, "substitution_psychology", "player",
                 player_off_id, "; ".join(effects), float(-minute // 10))

        return effects


# ── System 5: Late Goal Drama ──────────────────────────────────────────────


class LateGoalDrama:
    """Late goals (85+ min) have amplified psychological impact."""

    @staticmethod
    def process_late_goal(
        session: Session, scoring_club_id: int, conceding_club_id: int,
        minute: int, was_equalizer: bool, was_winner: bool,
        scorer_id: int | None,
        season: int, matchday: int,
    ) -> list[str]:
        """Process the amplified impact of late goals."""
        effects: list[str] = []
        if minute < 85:
            return effects

        # Injury time multiplier
        time_mult = 1.5 if minute >= 90 else 1.0

        scoring_squad = session.query(Player).filter_by(club_id=scoring_club_id).all()
        conceding_squad = session.query(Player).filter_by(club_id=conceding_club_id).all()

        if was_equalizer:
            # Scoring team: morale +5, spirit +3
            for p in scoring_squad:
                p.morale = clamp(p.morale + 5 * time_mult, 0.0, 100.0)
            scoring_club = session.get(Club, scoring_club_id)
            if scoring_club:
                scoring_club.team_spirit = clamp(
                    scoring_club.team_spirit + 3 * time_mult, 0.0, 100.0
                )

            # Conceding team: morale -8
            for p in conceding_squad:
                p.morale = clamp(p.morale - 8 * time_mult, 0.0, 100.0)
            # GK penalty
            conceding_gks = [p for p in conceding_squad if p.position == "GK"]
            for gk in conceding_gks:
                gk.morale = clamp(gk.morale - 5 * time_mult, 0.0, 100.0)

            effects.append(
                f"Late equalizer (min {minute}) — scoring team morale +{5*time_mult:.0f}, "
                f"conceding team morale -{8*time_mult:.0f}"
            )

        if was_winner:
            # Scoring team: morale +10, team_spirit +5
            for p in scoring_squad:
                p.morale = clamp(p.morale + 10 * time_mult, 0.0, 100.0)
            scoring_club = session.get(Club, scoring_club_id)
            if scoring_club:
                scoring_club.team_spirit = clamp(
                    scoring_club.team_spirit + 5 * time_mult, 0.0, 100.0
                )

            # Conceding team: morale -10, team_spirit -5
            for p in conceding_squad:
                p.morale = clamp(p.morale - 10 * time_mult, 0.0, 100.0)
            conceding_club = session.get(Club, conceding_club_id)
            if conceding_club:
                conceding_club.team_spirit = clamp(
                    conceding_club.team_spirit - 5 * time_mult, 0.0, 100.0
                )

            # Goal scorer: hero
            if scorer_id:
                scorer = session.get(Player, scorer_id)
                if scorer:
                    scorer.form = clamp(scorer.form + 8, 0.0, 100.0)
                    scorer.fan_favorite = True

            scorer_name = "Unknown"
            if scorer_id:
                s = session.get(Player, scorer_id)
                if s:
                    scorer_name = s.short_name or s.name

            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"INCREDIBLE! {scorer_name} scores in the {minute}th minute!",
                body=f"Dramatic scenes as {scorer_name} scored a last-gasp winner "
                     f"to send the fans into delirium.",
                category="match",
            ))
            effects.append(
                f"Late winner (min {minute}) — scoring team morale +{10*time_mult:.0f}, "
                f"conceding team morale -{10*time_mult:.0f}"
            )

        if effects:
            _log(session, season, matchday, "late_goal_drama", "club",
                 scoring_club_id, "; ".join(effects), 10.0 * time_mult)

        return effects


# ── System 6: Comeback Victories & Collapses ──────────────────────────────


class ComebackMechanics:
    """Coming from behind or collapsing from ahead has lasting effects."""

    @staticmethod
    def process_comeback(
        session: Session, club_id: int,
        goals_behind_at_max: int, goals_ahead_at_max: int,
        final_result: str, goal_diff: int,
        season: int, matchday: int,
    ) -> list[str]:
        """Process comeback victory or collapse.

        *final_result* is ``'W'``, ``'D'``, or ``'L'``.
        *goals_behind_at_max*: max deficit during match (positive = was losing).
        *goals_ahead_at_max*: max lead during match (positive = was winning).
        """
        effects: list[str] = []
        club = session.get(Club, club_id)
        if not club:
            return effects

        squad = session.query(Player).filter_by(club_id=club_id).all()
        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()

        # ── Comeback win (was 2+ goals behind, won) ──
        if goals_behind_at_max >= 2 and final_result == "W":
            for p in squad:
                p.morale = clamp(p.morale + 12, 0.0, 100.0)
            club.team_spirit = clamp(club.team_spirit + 8, 0.0, 100.0)
            if board:
                board.board_confidence = clamp(board.board_confidence + 3, 0.0, 100.0)
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"Remarkable comeback by {club.name}!",
                body=f"{club.name} were {goals_behind_at_max} goals down "
                     f"but fought back to win in extraordinary fashion.",
                category="match",
            ))
            effects.append(
                f"{club.name}: Comeback win from {goals_behind_at_max} down — "
                f"morale +12, spirit +8, board +3"
            )

        # ── Comeback draw (was 2+ behind, drew) ──
        elif goals_behind_at_max >= 2 and final_result == "D":
            for p in squad:
                p.morale = clamp(p.morale + 5, 0.0, 100.0)
                p.determination = min(99, (p.determination or 50) + 2)
            effects.append(
                f"{club.name}: Comeback draw from {goals_behind_at_max} down — morale +5, determination +2"
            )

        # ── Collapse (was 2+ ahead, lost) ──
        elif goals_ahead_at_max >= 2 and final_result == "L":
            for p in squad:
                p.morale = clamp(p.morale - 15, 0.0, 100.0)
            club.team_spirit = clamp(club.team_spirit - 10, 0.0, 100.0)
            if board:
                board.board_confidence = clamp(board.board_confidence - 5, 0.0, 100.0)
                board.fan_happiness = clamp(board.fan_happiness - 8, 0.0, 100.0)

            # Defenders extra penalty
            defenders = [p for p in squad if p.position in ("CB", "LB", "RB", "LWB", "RWB")]
            for p in defenders:
                p.morale = clamp(p.morale - 5, 0.0, 100.0)

            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"Capitulation! {club.name} throw away {goals_ahead_at_max}-goal lead",
                body=f"{club.name} were cruising at {goals_ahead_at_max} goals ahead "
                     f"but collapsed to lose the match.",
                category="match",
            ))
            effects.append(
                f"{club.name}: Collapse from {goals_ahead_at_max} ahead — "
                f"morale -15, spirit -10, board -5, fans -8"
            )

        # ── Collapse draw (was 2+ ahead, drew) ──
        elif goals_ahead_at_max >= 2 and final_result == "D":
            for p in squad:
                p.morale = clamp(p.morale - 8, 0.0, 100.0)
            club.team_spirit = clamp(club.team_spirit - 5, 0.0, 100.0)
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"Points thrown away by {club.name}",
                body=f"{club.name} led by {goals_ahead_at_max} goals but could "
                     f"only manage a draw.",
                category="match",
            ))
            effects.append(
                f"{club.name}: Collapse draw from {goals_ahead_at_max} ahead — morale -8, spirit -5"
            )

        if effects:
            mag = 12.0 if final_result == "W" else -15.0 if final_result == "L" else 0.0
            _log(session, season, matchday, "comeback_mechanics", "club",
                 club_id, "; ".join(effects), mag)

        return effects


# ── System 7: Fixture Congestion & Fatigue ─────────────────────────────────


class FixtureCongestion:
    """Playing too many matches in a short period causes fatigue and injuries."""

    @staticmethod
    def check_congestion(
        session: Session, club_id: int, season: int, matchday: int,
    ) -> int:
        """Return number of matches played in last 3 matchdays (including cups)."""
        from fm.db.models import CupFixture
        low_md = max(1, matchday - 2)

        league_count = session.query(Fixture).filter(
            Fixture.season == season,
            Fixture.matchday.between(low_md, matchday),
            Fixture.played == True,  # noqa: E712
            (Fixture.home_club_id == club_id) | (Fixture.away_club_id == club_id),
        ).count()

        cup_count = session.query(CupFixture).filter(
            CupFixture.season == season,
            CupFixture.played == True,  # noqa: E712
            (CupFixture.home_club_id == club_id) | (CupFixture.away_club_id == club_id),
        ).count()

        return league_count + cup_count

    @staticmethod
    def apply_congestion_effects(
        session: Session, club_id: int, congestion_level: int,
        season: int, matchday: int,
    ) -> list[str]:
        """Apply fatigue and injury risk from congestion."""
        effects: list[str] = []
        if congestion_level < 3:
            return effects

        club = session.get(Club, club_id)
        squad = session.query(Player).filter_by(club_id=club_id).all()

        if congestion_level >= 3:
            for p in squad:
                p.fitness = clamp((p.fitness or 100) - 5, 0.0, 100.0)
                p.injury_proneness = min(99, (p.injury_proneness or 30) + 10)
            if club:
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"Grueling schedule taking its toll on {club.name}",
                    body=f"{club.name} have played {congestion_level} matches in "
                         f"3 matchdays. The squad is feeling the strain.",
                    category="general",
                ))
            effects.append(
                f"{club.name if club else club_id}: Congestion {congestion_level} — "
                f"fitness -5, injury proneness +10"
            )

        if congestion_level >= 4:
            for p in squad:
                p.fitness = clamp((p.fitness or 100) - 5, 0.0, 100.0)  # extra -5
                p.injury_proneness = min(99, (p.injury_proneness or 30) + 10)  # extra
                p.morale = clamp(p.morale - 3, 0.0, 100.0)
            if club:
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"Manager calls for rest after punishing schedule",
                    body=f"{club.name} face fixture overload with {congestion_level} "
                         f"matches in rapid succession.",
                    category="general",
                ))
            effects.append(
                f"{club.name if club else club_id}: Severe congestion {congestion_level} — "
                f"extra fitness -5, morale -3"
            )

        if effects:
            _log(session, season, matchday, "fixture_congestion", "club",
                 club_id, "; ".join(effects), float(-congestion_level))

        return effects


# ── System 8: Transfer Window Drama ───────────────────────────────────────


class TransferWindowDrama:
    """Transfer window creates unsettling period for clubs."""

    @staticmethod
    def process_window_open(
        session: Session, club_id: int, season: int, matchday: int,
    ) -> list[str]:
        """Effects while transfer window is open."""
        effects: list[str] = []
        squad = session.query(Player).filter_by(club_id=club_id).all()

        for p in squad:
            # Players wanting transfer: morale -2/week
            if p.wants_transfer:
                p.morale = clamp(p.morale - 2, 0.0, 100.0)
                effects.append(f"{p.name}: Unsettled during window — morale -2")

            # Low happiness + high ambition: agent activity
            if (p.happiness or 65) < 40 and (p.ambition or 50) > 70:
                p.trust_in_manager = clamp(
                    (p.trust_in_manager or 60) - 2, 0.0, 100.0
                )
                if random.random() < 0.05:
                    session.add(NewsItem(
                        season=season, matchday=matchday,
                        headline=f"{p.short_name or p.name}'s agent approaches rival club",
                        body=f"The agent of {p.name} is reportedly in talks with other clubs.",
                        category="transfer",
                    ))
                    effects.append(f"{p.name}: Agent approaching rivals")

        return effects

    @staticmethod
    def process_deadline_day(
        session: Session, club_id: int, season: int, matchday: int,
    ) -> list[str]:
        """Last day of transfer window — heightened drama."""
        effects: list[str] = []
        club = session.get(Club, club_id)
        squad = session.query(Player).filter_by(club_id=club_id).all()

        # All unsettled players: final morale swing
        for p in squad:
            if p.wants_transfer:
                p.morale = clamp(p.morale - 5, 0.0, 100.0)
                effects.append(f"{p.name}: Deadline day — still unsettled, morale -5")
            else:
                p.morale = clamp(p.morale + 1, 0.0, 100.0)

        if club:
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"Deadline day drama at {club.name}",
                body=f"The transfer window slams shut with {club.name} scrambling to finalize deals.",
                category="transfer",
            ))

        effects.append(f"Deadline day at {club.name if club else club_id}")
        return effects


# ── System 9: Veteran Decline & Retirement ─────────────────────────────────


class VeteranDecline:
    """Aging players face decline, retirement decisions, and legacy moments."""

    @staticmethod
    def process_aging(session: Session, player_id: int, season: int) -> list[str]:
        """Seasonal aging effects for 30+ players."""
        effects: list[str] = []
        player = session.get(Player, player_id)
        if not player:
            return effects
        age = player.age or 25
        if age < 30:
            return effects

        club = session.get(Club, player.club_id) if player.club_id else None
        club_name = club.name if club else "their club"

        # Age 30-32: Managing the body
        if 30 <= age <= 32:
            player.injury_proneness = min(99, (player.injury_proneness or 30) + 3)
            # Mental attributes improve with experience
            player.composure = min(99, (player.composure or 50) + 1)
            player.positioning = min(99, (player.positioning or 50) + 1)
            effects.append(
                f"{player.name} (age {age}): Managing the body — "
                f"injury proneness +3, composure +1, positioning +1"
            )

        # Age 33-35: Racing against time
        elif 33 <= age <= 35:
            player.pace = max(1, (player.pace or 50) - 2)
            player.acceleration = max(1, (player.acceleration or 50) - 2)
            player.stamina = max(1, (player.stamina or 50) - 2)
            player.sprint_speed = max(1, (player.sprint_speed or 50) - 3)
            player.injury_proneness = min(99, (player.injury_proneness or 30) + 5)
            effects.append(
                f"{player.name} (age {age}): Racing against time — "
                f"pace -2, acceleration -2, stamina -2, sprint_speed -3, injury +5"
            )

            if (player.form or 65) > 70:
                session.add(NewsItem(
                    season=season, matchday=0,
                    headline=f"{player.short_name or player.name} defying age at {club_name}",
                    body=f"At {age}, {player.name} continues to perform at a high level.",
                    category="general",
                ))

        # Age 36+: Last dance
        elif age >= 36:
            player.pace = max(1, (player.pace or 50) - 3)
            player.acceleration = max(1, (player.acceleration or 50) - 3)
            player.stamina = max(1, (player.stamina or 50) - 3)
            player.sprint_speed = max(1, (player.sprint_speed or 50) - 3)
            player.physical = max(1, (player.physical or 50) - 3)
            player.injury_proneness = min(99, (player.injury_proneness or 30) + 5)
            effects.append(
                f"{player.name} (age {age}): Last dance — "
                f"all physicals -3, injury +5"
            )

            if (player.minutes_season or 0) > 1500:
                session.add(NewsItem(
                    season=season, matchday=0,
                    headline=f"Remarkable longevity for {player.short_name or player.name}",
                    body=f"At {age}, {player.name} is still a regular starter at {club_name}.",
                    category="general",
                ))

        if effects:
            _log(session, season, 0, "veteran_decline", "player",
                 player_id, "; ".join(effects), float(-(age - 29)))

        return effects

    @staticmethod
    def check_retirement(session: Session, player_id: int) -> bool:
        """Check if player should retire. Returns True if retiring."""
        player = session.get(Player, player_id)
        if not player:
            return False

        age = player.age or 25
        if age < 33:
            return False

        # Base probability by age
        base_probs = {
            33: 0.02, 34: 0.05, 35: 0.10, 36: 0.20,
            37: 0.35, 38: 0.50, 39: 0.75, 40: 0.95,
        }
        prob = base_probs.get(age, 1.0 if age > 40 else 0.0)

        # Modifiers
        if (player.determination or 50) > 80:
            prob -= 0.10
        if (player.professionalism or 50) > 80:
            prob -= 0.05
        if (player.injured_weeks or 0) > 26:
            prob += 0.15
        if (player.minutes_season or 0) > 1800:
            prob -= 0.10

        prob = max(0.0, min(1.0, prob))

        if random.random() < prob:
            club = session.get(Club, player.club_id) if player.club_id else None
            club_name = club.name if club else "football"
            session.add(NewsItem(
                season=0, matchday=0,
                headline=f"{player.short_name or player.name} announces retirement",
                body=f"{player.name}, aged {age}, has decided to hang up "
                     f"his boots after a long career at {club_name}.",
                category="general",
            ))
            return True

        return False


# ── System 10: Cup Giant Killing ───────────────────────────────────────────


class CupGiantKilling:
    """When a lower-rated team beats a much higher-rated team in a cup."""

    @staticmethod
    def process_cup_result(
        session: Session, winner_id: int, loser_id: int,
        is_cup: bool, season: int, matchday: int,
    ) -> list[str]:
        """Process cup result for giant-killing effects."""
        effects: list[str] = []
        if not is_cup:
            return effects

        winner = session.get(Club, winner_id)
        loser = session.get(Club, loser_id)
        if not winner or not loser:
            return effects

        rep_gap = (loser.reputation or 50) - (winner.reputation or 50)

        # Giant killing (rep gap > 25)
        if rep_gap > 25:
            # Winner effects
            winner_squad = session.query(Player).filter_by(club_id=winner_id).all()
            for p in winner_squad:
                p.morale = clamp(p.morale + 10, 0.0, 100.0)
                p.big_match = min(99, (p.big_match or 50) + 2)
            winner.team_spirit = clamp(winner.team_spirit + 8, 0.0, 100.0)
            winner_board = session.query(BoardExpectation).filter_by(club_id=winner_id).first()
            if winner_board:
                winner_board.fan_happiness = clamp(winner_board.fan_happiness + 10, 0.0, 100.0)
                winner_board.board_confidence = clamp(winner_board.board_confidence + 5, 0.0, 100.0)

            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"CUPSET! {winner.name} stun {loser.name}!",
                body=f"Underdogs {winner.name} produced a stunning cup upset "
                     f"to knock out {loser.name}.",
                category="cup",
            ))
            effects.append(
                f"{winner.name}: Giant killing — morale +10, spirit +8, "
                f"big_match +2, fans +10, board +5"
            )

            # Loser effects (embarrassment)
            loser_squad = session.query(Player).filter_by(club_id=loser_id).all()
            for p in loser_squad:
                p.morale = clamp(p.morale - 12, 0.0, 100.0)
            loser.team_spirit = clamp(loser.team_spirit - 8, 0.0, 100.0)
            loser_board = session.query(BoardExpectation).filter_by(club_id=loser_id).first()
            if loser_board:
                loser_board.fan_happiness = clamp(loser_board.fan_happiness - 10, 0.0, 100.0)
                loser_board.board_confidence = clamp(loser_board.board_confidence - 8, 0.0, 100.0)

            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"{loser.name} humiliated in cup shock",
                body=f"{loser.name} suffered a humiliating cup exit at "
                     f"the hands of {winner.name}.",
                category="cup",
            ))

            # Stars with ambition > 75: trust eroded
            ambitious_stars = [
                p for p in loser_squad
                if (p.ambition or 50) > 75
            ]
            for p in ambitious_stars:
                p.trust_in_manager = clamp(
                    (p.trust_in_manager or 60) - 5, 0.0, 100.0
                )

            effects.append(
                f"{loser.name}: Cup humiliation — morale -12, spirit -8, "
                f"fans -10, board -8"
            )

        if effects:
            _log(session, season, matchday, "cup_giant_killing", "club",
                 winner_id, "; ".join(effects), float(rep_gap))

        return effects


# ── System 11: Agent Interference ──────────────────────────────────────────


class AgentInterference:
    """Agents destabilize players to force moves or wage increases."""

    @staticmethod
    def process_agent_activity(
        session: Session, club_id: int, season: int, matchday: int,
    ) -> list[str]:
        """Run monthly. Agents may approach players."""
        effects: list[str] = []
        squad = session.query(Player).filter_by(club_id=club_id).all()

        for p in squad:
            # Contract expiry within 2 seasons
            if (p.contract_expiry or 2030) <= season + 2:
                if (p.overall or 50) > 75 and (p.ambition or 50) > 65:
                    if random.random() < 0.10:
                        p.happiness = clamp((p.happiness or 65) - 3, 0.0, 100.0)
                        p.trust_in_manager = clamp(
                            (p.trust_in_manager or 60) - 2, 0.0, 100.0
                        )
                        session.add(NewsItem(
                            season=season, matchday=matchday,
                            headline=f"Agent advises {p.short_name or p.name} to seek bigger club",
                            body=f"The agent of {p.name} is reportedly encouraging "
                                 f"a move away, with the contract expiring soon.",
                            category="transfer",
                        ))
                        effects.append(
                            f"{p.name}: Agent activity — happiness -3, trust -2"
                        )

            # Star players in great form
            if (p.overall or 50) > 82 and (p.form or 65) > 75:
                if random.random() < 0.05:
                    session.add(NewsItem(
                        season=season, matchday=matchday,
                        headline=f"Agent hints at interest from top clubs for {p.short_name or p.name}",
                        body=f"Interest is reportedly building in {p.name} "
                             f"following a run of outstanding performances.",
                        category="transfer",
                    ))
                    effects.append(f"{p.name}: Agent hinting at moves")

            # Strikers with 0 goals in 10+ matches
            if p.position in ("ST", "CF") and (p.goals_season or 0) == 0:
                if (p.minutes_season or 0) > 900:  # ~10 full matches
                    if random.random() < 0.08:
                        session.add(NewsItem(
                            season=season, matchday=matchday,
                            headline=f"{p.short_name or p.name}'s agent opens talks with rival clubs",
                            body=f"With zero goals this season, {p.name}'s agent "
                                 f"is looking for a fresh start elsewhere.",
                            category="transfer",
                        ))
                        effects.append(f"{p.name}: Agent seeking move due to goal drought")

        return effects


# ── System 12: Weather & Season Effects ────────────────────────────────────


class SeasonalEffects:
    """Time of year affects gameplay, injuries, and morale."""

    @staticmethod
    def get_season_effects(matchday: int) -> dict:
        """Return modifiers based on time of season."""
        effects = {
            "injury_proneness_mod": 0,
            "importance_multiplier": 0.0,
            "fitness_recovery_mod": 0.0,
            "morale_volatility": 1.0,
            "phase": "normal",
        }

        # Matchday 1-6 (Aug-Sep): Early season
        if matchday <= 6:
            effects["phase"] = "early_season"
            effects["fitness_recovery_mod"] = -0.05
            # Players not fully sharp yet

        # Matchday 7-15 (Oct-Dec): Autumn grind
        elif matchday <= 15:
            effects["phase"] = "autumn"
            # Normal play

        # Matchday 16-22 (Dec-Jan): Winter
        elif matchday <= 22:
            effects["phase"] = "winter"
            effects["injury_proneness_mod"] = 10
            effects["morale_volatility"] = 1.3
            # Cold weather muscle injuries, fixture congestion peak

        # Matchday 23-30 (Feb-Mar): Business end
        elif matchday <= 30:
            effects["phase"] = "business_end"
            effects["importance_multiplier"] = 0.1
            effects["morale_volatility"] = 1.2

        # Matchday 31-38 (Apr-May): Run-in
        else:
            effects["phase"] = "run_in"
            effects["importance_multiplier"] = 0.2
            effects["morale_volatility"] = 1.5
            effects["fitness_recovery_mod"] = -0.20

        return effects

    @staticmethod
    def apply_seasonal_effects(
        session: Session, club_id: int, season: int, matchday: int,
    ) -> list[str]:
        """Apply seasonal modifiers to the squad."""
        effects_list: list[str] = []
        fx = SeasonalEffects.get_season_effects(matchday)

        squad = session.query(Player).filter_by(club_id=club_id).all()

        if fx["injury_proneness_mod"] > 0:
            for p in squad:
                p.injury_proneness = min(
                    99, (p.injury_proneness or 30) + fx["injury_proneness_mod"]
                )
            effects_list.append(
                f"Winter conditions — injury proneness +{fx['injury_proneness_mod']}"
            )

        # Players with few appearances: morale drop in business end
        if fx["phase"] in ("business_end", "run_in"):
            for p in squad:
                if (p.minutes_season or 0) < 450:  # <5 full matches = ~15 appearances threshold
                    p.morale = clamp(p.morale - 3, 0.0, 100.0)
            effects_list.append(
                f"Season phase '{fx['phase']}' — low-appearance players frustrated"
            )

        return effects_list


# ── System 13: Penalty Shootout Trauma ─────────────────────────────────────


class PenaltyTrauma:
    """Missing a penalty in a shootout creates lasting psychological scars."""

    @staticmethod
    def process_penalty_miss(
        session: Session, player_id: int,
        was_decisive: bool, is_cup_exit: bool,
        season: int, matchday: int,
    ) -> list[str]:
        """Process the psychological impact of a penalty miss."""
        effects: list[str] = []
        player = session.get(Player, player_id)
        if not player:
            return effects

        composure = player.composure or 50
        # High composure (>85): all effects halved
        mult = 0.5 if composure > 85 else 1.0

        if was_decisive and is_cup_exit:
            # Decisive shootout miss (team eliminated because of this miss)
            player.morale = clamp(player.morale - 15 * mult, 0.0, 100.0)
            player.composure = max(1, int(composure - 5 * mult))
            player.penalties = max(1, (player.penalties or 50) - int(5 * mult))
            player.big_match = max(1, (player.big_match or 50) - 2)

            # Team morale hit
            if player.club_id:
                team = session.query(Player).filter(
                    Player.club_id == player.club_id,
                    Player.id != player_id,
                ).all()
                for p in team:
                    p.morale = clamp(p.morale - 8 * mult, 0.0, 100.0)

            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"{player.short_name or player.name} devastated after shootout heartbreak",
                body=f"{player.name}'s decisive penalty miss sent his team crashing "
                     f"out of the cup. The psychological scars may take time to heal.",
                category="cup",
            ))
            effects.append(
                f"{player.name}: Decisive miss — morale -{15*mult:.0f}, composure -{5*mult:.0f}, "
                f"penalties -{5*mult:.0f}, big_match -2, team morale -{8*mult:.0f}"
            )

        elif is_cup_exit and not was_decisive:
            # Shootout miss (non-decisive)
            player.morale = clamp(player.morale - 8 * mult, 0.0, 100.0)
            player.penalties = max(1, (player.penalties or 50) - int(3 * mult))
            player.composure = max(1, int(composure - 3 * mult))
            effects.append(
                f"{player.name}: Shootout miss — morale -{8*mult:.0f}, "
                f"penalties -{3*mult:.0f}, composure -{3*mult:.0f}"
            )

        else:
            # Regular penalty miss in match
            player.morale = clamp(player.morale - 5 * mult, 0.0, 100.0)
            player.composure = max(1, int(composure - 2 * mult))
            effects.append(
                f"{player.name}: Penalty miss — morale -{5*mult:.0f}, composure -{2*mult:.0f}"
            )

        if effects:
            _log(session, season, matchday, "penalty_trauma", "player",
                 player_id, "; ".join(effects), -15.0 * mult if was_decisive else -5.0 * mult)

        return effects


# ── System 14: Managerial Mind Games ───────────────────────────────────────


class ManagerMindGames:
    """Pre-match comments and media interactions affect psychology."""

    COMMENT_TYPES = {
        "praise_opponent": {"own_composure": 0.02, "opp_composure": 0.01},
        "dismiss_opponent": {"own_morale": 2, "opp_morale": 3},  # motivates them!
        "mind_games": {"own_composure": -0.01, "opp_composure": -0.03},
        "deflect_pressure": {"own_morale": 1, "own_composure": 0.02},
        "call_for_fans": {"home_boost": 0.03, "fan_happiness": 1},
        "demand_respect": {"own_morale": 3, "opp_aggression": 3},
        "stay_humble": {"own_composure": 0.03, "board_confidence": 1},
        "attack_referee": {"own_cards_risk": 0.02, "fan_happiness": 2, "board_conf": -1},
    }

    _COMMENT_TEMPLATES = {
        "praise_opponent": "We have great respect for {opponent}. They are a quality side.",
        "dismiss_opponent": "I don't think {opponent} can live with us on our day.",
        "mind_games": "I'm not sure {opponent} can handle the pressure of this fixture.",
        "deflect_pressure": "The pressure is all on {opponent}. We have nothing to lose.",
        "call_for_fans": "We need our fans to be our 12th man this weekend.",
        "demand_respect": "People need to start giving {club} the respect we deserve.",
        "stay_humble": "We're taking it one game at a time. No looking ahead.",
        "attack_referee": "I hope the officials get the big decisions right this time.",
    }

    @staticmethod
    def apply_pre_match_comment(
        session: Session, club_id: int, opponent_id: int,
        comment_type: str, season: int, matchday: int,
    ) -> list[str]:
        """Apply effects of pre-match managerial comment."""
        effects_list: list[str] = []
        cfg = ManagerMindGames.COMMENT_TYPES.get(comment_type)
        if not cfg:
            return effects_list

        club = session.get(Club, club_id)
        opponent = session.get(Club, opponent_id)
        if not club or not opponent:
            return effects_list

        own_squad = session.query(Player).filter_by(club_id=club_id).all()
        opp_squad = session.query(Player).filter_by(club_id=opponent_id).all()
        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()

        # Apply own team effects
        own_morale = cfg.get("own_morale", 0)
        own_composure = cfg.get("own_composure", 0)
        if own_morale:
            for p in own_squad:
                p.morale = clamp(p.morale + own_morale, 0.0, 100.0)
        if own_composure:
            for p in own_squad:
                p.composure = max(1, min(99, int((p.composure or 50) + own_composure * 100)))

        # Apply opponent effects
        opp_morale = cfg.get("opp_morale", 0)
        opp_composure = cfg.get("opp_composure", 0)
        opp_aggression = cfg.get("opp_aggression", 0)
        if opp_morale:
            for p in opp_squad:
                p.morale = clamp(p.morale + opp_morale, 0.0, 100.0)
        if opp_composure:
            for p in opp_squad:
                p.composure = max(1, min(99, int((p.composure or 50) + opp_composure * 100)))
        if opp_aggression:
            for p in opp_squad:
                p.aggression = min(99, (p.aggression or 50) + opp_aggression)

        # Board/fan effects
        if cfg.get("fan_happiness") and board:
            board.fan_happiness = clamp(
                board.fan_happiness + cfg["fan_happiness"], 0.0, 100.0
            )
        if cfg.get("board_confidence") and board:
            board.board_confidence = clamp(
                board.board_confidence + cfg["board_confidence"], 0.0, 100.0
            )
        if cfg.get("board_conf") and board:
            board.board_confidence = clamp(
                board.board_confidence + cfg["board_conf"], 0.0, 100.0
            )

        # Generate news
        template = ManagerMindGames._COMMENT_TEMPLATES.get(
            comment_type, "The manager had words before the match."
        )
        quote = template.format(
            opponent=opponent.name, club=club.name,
        )
        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"Pre-match: {club.name} boss speaks",
            body=f'Manager says: "{quote}"',
            category="manager",
        ))

        effects_list.append(f"Mind games ({comment_type}): {quote}")

        _log(session, season, matchday, "mind_games", "club",
             club_id, "; ".join(effects_list), float(own_morale))

        return effects_list
