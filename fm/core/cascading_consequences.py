"""Deep cascading consequence systems for realistic football dynamics.

Six interconnected systems that create emergent storylines:
1. FormSpiral — win/loss streaks trigger cascading morale and board effects
2. DressingRoomPolitics — squad harmony, factions, and power dynamics
3. InjuryCascade — injury pile-ups trigger medical crisis and ripple effects
4. FinancialPressure — financial distress forces painful decisions
5. ManagerJobSecurity — models realistic sacking probability
6. CascadingNarrativeEngine — detects and applies multi-matchday narrative arcs
"""
from __future__ import annotations

import random
from collections import Counter

from sqlalchemy.orm import Session

from fm.db.models import (
    BoardExpectation,
    Club,
    ConsequenceLog,
    Injury,
    LeagueStanding,
    NewsItem,
    Player,
    TacticalSetup,
)
from fm.utils.helpers import clamp


# ── System 1: Form Spiral & Momentum Streaks ───────────────────────────────


class FormSpiral:
    """Tracks streaks and triggers cascading morale/form effects."""

    @staticmethod
    def process_streak(session: Session, club_id: int, result: str, matchday: int, season: int) -> list[str]:
        """Call after each match. *result* is ``'W'``, ``'D'``, or ``'L'``.

        Returns list of effect descriptions for logging/news.
        """
        effects: list[str] = []

        standing = (
            session.query(LeagueStanding)
            .filter_by(club_id=club_id, season=season)
            .first()
        )
        if standing is None:
            return effects

        form_str = standing.form or ""

        # Count consecutive same results from the end
        streak_len = 0
        for ch in reversed(form_str):
            if ch == result:
                streak_len += 1
            else:
                break

        club = session.get(Club, club_id)
        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()
        squad = session.query(Player).filter_by(club_id=club_id).all()

        if result == "W":
            effects.extend(
                FormSpiral._process_winning_streak(session, club, board, squad, streak_len, matchday, season)
            )
        elif result == "L":
            effects.extend(
                FormSpiral._process_losing_streak(session, club, board, squad, streak_len, matchday, season)
            )
        elif result == "D":
            effects.extend(
                FormSpiral._process_drawing_streak(session, club, board, squad, streak_len, matchday, season)
            )

        return effects

    @staticmethod
    def _process_winning_streak(
        session: Session, club: Club | None, board: BoardExpectation | None,
        squad: list[Player], streak: int, matchday: int, season: int,
    ) -> list[str]:
        effects: list[str] = []
        if streak < 3 or club is None:
            return effects

        if streak >= 3:
            for p in squad:
                p.morale = clamp(p.morale + 3, 0.0, 100.0)
            if club is not None:
                club.team_spirit = clamp(club.team_spirit + 2, 0.0, 100.0)
            effects.append(f"{club.name}: Good run of form — squad morale +3, spirit +2")

        if streak >= 5:
            for p in squad:
                p.morale = clamp(p.morale + 2, 0.0, 100.0)  # additional +2 on top of the +3
            if club is not None:
                club.team_spirit = clamp(club.team_spirit + 3, 0.0, 100.0)
            if board is not None:
                board.board_confidence = clamp(board.board_confidence + 3, 0.0, 100.0)
            effects.append(f"{club.name}: 5-match winning streak — board confidence +3")

        if streak >= 8:
            for p in squad:
                p.morale = clamp(p.morale + 3, 0.0, 100.0)
            if board is not None:
                board.fan_happiness = clamp(board.fan_happiness + 5, 0.0, 100.0)
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"{club.name}'s unbeaten run continues!",
                body=f"{club.name} have now won {streak} matches in a row — "
                     f"opponents are starting to fear them.",
                category="general",
            ))
            effects.append(f"{club.name}: {streak}-match winning streak — fan happiness +5, fear factor active")

        # Log
        _log(session, season, matchday, "winning_streak", "club", club.id,
             "; ".join(effects), float(streak))

        return effects

    @staticmethod
    def _process_losing_streak(
        session: Session, club: Club | None, board: BoardExpectation | None,
        squad: list[Player], streak: int, matchday: int, season: int,
    ) -> list[str]:
        effects: list[str] = []
        if streak < 2 or club is None:
            return effects

        if streak >= 2:
            for p in squad:
                p.morale = clamp(p.morale - 3, 0.0, 100.0)
            effects.append(f"{club.name}: Wobble — squad morale -3 after {streak} losses")

        if streak >= 3:
            if club is not None:
                club.team_spirit = clamp(club.team_spirit - 5, 0.0, 100.0)
            if board is not None:
                board.board_confidence = clamp(board.board_confidence - 5, 0.0, 100.0)
            effects.append(f"{club.name}: 3-loss streak — spirit -5, board confidence -5, media pressure")

        if streak >= 5:
            for p in squad:
                p.morale = clamp(p.morale - 7, 0.0, 100.0)  # additional on top of -3
            if club is not None:
                club.team_spirit = clamp(club.team_spirit - 5, 0.0, 100.0)
            if board is not None:
                board.board_confidence = clamp(board.board_confidence - 5, 0.0, 100.0)
                board.fan_happiness = clamp(board.fan_happiness - 8, 0.0, 100.0)

            # Players with low trust may trigger dressing room tension
            low_trust = [p for p in squad if (p.trust_in_manager or 60) < 30]
            if low_trust:
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"Dressing room tension at {club.name}",
                    body=f"After {streak} consecutive defeats, unrest is brewing "
                         f"at {club.name}. Several players have lost faith.",
                    category="manager",
                ))

            # Ambitious players want out
            ambitious = [p for p in squad if (p.ambition or 50) > 70]
            for p in ambitious:
                p.wants_transfer = True
            if ambitious:
                effects.append(f"{club.name}: {len(ambitious)} ambitious players want transfers")

            effects.append(f"{club.name}: 5-loss streak — morale -10, spirit -10, confidence -10")

        if streak >= 7:
            if board is not None:
                board.board_confidence = clamp(board.board_confidence - 10, 0.0, 100.0)
                board.fan_happiness = clamp(board.fan_happiness - 7, 0.0, 100.0)
                if not board.ultimatum_active:
                    board.ultimatum_active = True
                    session.add(NewsItem(
                        season=season, matchday=matchday,
                        headline=f"Board issues ultimatum to {club.name} boss",
                        body=f"After {streak} straight defeats, the board at {club.name} "
                             f"have issued an ultimatum to the manager.",
                        category="manager",
                    ))
            # 3 random players request transfer
            eligible = [p for p in squad if not p.wants_transfer]
            for p in random.sample(eligible, min(3, len(eligible))):
                p.wants_transfer = True

            effects.append(f"{club.name}: 7-loss streak — ultimatum, transfer requests")

        _log(session, season, matchday, "losing_streak", "club", club.id,
             "; ".join(effects), float(-streak))

        return effects

    @staticmethod
    def _process_drawing_streak(
        session: Session, club: Club | None, board: BoardExpectation | None,
        squad: list[Player], streak: int, matchday: int, season: int,
    ) -> list[str]:
        effects: list[str] = []
        if streak < 4 or club is None:
            return effects

        if board is not None:
            board.fan_happiness = clamp(board.fan_happiness - 3, 0.0, 100.0)
        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"Fans frustrated with stale football at {club.name}",
            body=f"{club.name} have drawn {streak} matches in a row. "
                 f"Fans are growing restless with the lack of decisive results.",
            category="general",
        ))
        effects.append(f"{club.name}: {streak} consecutive draws — fan happiness -3")

        _log(session, season, matchday, "drawing_streak", "club", club.id,
             "; ".join(effects), float(-streak))

        return effects


# ── System 2: Dressing Room Politics ────────────────────────────────────────


class DressingRoomPolitics:
    """Models squad harmony, factions, and player power dynamics."""

    TENSION_THRESHOLD = 3
    MUTINY_THRESHOLD = 5

    @staticmethod
    def process_squad_harmony(session: Session, club_id: int, season: int, matchday: int = 0) -> str:
        """Run weekly. Checks for faction formation and power struggles.

        Returns the dressing room state: ``'calm'``, ``'tension'``, or ``'mutiny'``.
        """
        squad = session.query(Player).filter_by(club_id=club_id).all()
        if not squad:
            return "calm"

        club = session.get(Club, club_id)
        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()

        unhappy = [
            p for p in squad
            if (p.happiness or 65) < 40 or (p.trust_in_manager or 60) < 30
        ]
        num_unhappy = len(unhappy)

        # Detect captain
        tac = session.query(TacticalSetup).filter_by(club_id=club_id).first()
        captain_id = tac.captain_id if tac else None
        captain_unhappy = any(p.id == captain_id for p in unhappy)
        multiplier = 1.5 if captain_unhappy else 1.0

        state = "calm"

        if num_unhappy >= DressingRoomPolitics.MUTINY_THRESHOLD:
            state = "mutiny"
            # Team talks completely ineffective — modelled by setting a very low modifier
            # Form modifier for all players
            for p in squad:
                p.form = clamp(p.form - 5.0 * multiplier, 0.0, 100.0)

            if board is not None:
                board.board_confidence = clamp(
                    board.board_confidence - 3 * multiplier, 0.0, 100.0
                )

            # Senior players may demand meeting
            seniors = [p for p in squad if (p.leadership or 50) > 70]
            if seniors:
                leader = max(seniors, key=lambda p: p.leadership or 50)
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"{leader.short_name or leader.name} demands crisis meeting at {club.name}",
                    body=f"Senior player {leader.name} has demanded a crisis meeting "
                         f"with management as squad unrest reaches boiling point.",
                    category="manager",
                ))

            _log(session, season, matchday, "dressing_room_mutiny", "club", club_id,
                 f"MUTINY: {num_unhappy} unhappy players, captain_unhappy={captain_unhappy}",
                 -15.0 * multiplier)

        elif num_unhappy >= DressingRoomPolitics.TENSION_THRESHOLD:
            state = "tension"
            # Training effectiveness reduced (modelled by small form hit)
            for p in squad:
                p.form = clamp(p.form - 2.0 * multiplier, 0.0, 100.0)

            # Random public criticism (10% chance)
            if random.random() < 0.10 and unhappy:
                critic = random.choice(unhappy)
                session.add(NewsItem(
                    season=season, matchday=matchday,
                    headline=f"{critic.short_name or critic.name} criticizes manager publicly",
                    body=f"{critic.name} has spoken out against the management at "
                         f"{club.name if club else 'the club'}, expressing frustration.",
                    category="manager",
                ))

            _log(session, season, matchday, "dressing_room_tension", "club", club_id,
                 f"TENSION: {num_unhappy} unhappy players, captain_unhappy={captain_unhappy}",
                 -8.0 * multiplier)

        return state

    @staticmethod
    def process_clique_dynamics(session: Session, club_id: int, season: int = 0, matchday: int = 0) -> list[str]:
        """Check nationality cliques for positive/negative effects.

        Returns list of effect descriptions.
        """
        effects: list[str] = []
        squad = session.query(Player).filter_by(club_id=club_id).all()
        if not squad:
            return effects

        # Group by nationality
        nat_groups: dict[str, list[Player]] = {}
        for p in squad:
            nat = p.nationality or "Unknown"
            nat_groups.setdefault(nat, []).append(p)

        for nat, members in nat_groups.items():
            if len(members) < 3:
                continue

            avg_morale = sum((p.morale or 65) for p in members) / len(members)

            if avg_morale > 75:
                # Positive clique — chemistry boost
                for p in members:
                    p.team_chemistry = clamp((p.team_chemistry or 50) + 2, 0.0, 100.0)
                effects.append(f"{nat} clique at club {club_id}: high morale — chemistry +2")

            elif avg_morale < 40:
                # Negative clique — outsider tension
                clique_ids = {p.id for p in members}
                for p in squad:
                    if p.id not in clique_ids:
                        p.morale = clamp(p.morale - 1, 0.0, 100.0)
                effects.append(f"{nat} clique at club {club_id}: low morale — outsider tension -1")

                # If clique leader unhappy, drag others down
                leader = max(members, key=lambda p: p.leadership or 50)
                leader_morale = leader.morale or 65
                if leader_morale < 40:
                    for p in members:
                        if p.id != leader.id:
                            p.morale = clamp(
                                min(p.morale, leader_morale + 5), 0.0, 100.0
                            )
                    effects.append(
                        f"{nat} clique leader {leader.short_name or leader.name} "
                        f"dragging clique morale down"
                    )

        return effects


# ── System 3: Injury Cascade & Medical Crisis ──────────────────────────────


class InjuryCascade:
    """Tracks injury patterns and triggers medical crisis effects."""

    @staticmethod
    def process_injury_impact(
        session: Session, club_id: int, injured_player_id: int,
        injury_type: str, severity: str, season: int, matchday: int,
    ) -> list[str]:
        """Called when a player gets injured. Returns effect descriptions."""
        effects: list[str] = []
        club = session.get(Club, club_id)
        if club is None:
            return effects

        # Count active injuries at the club
        active_injuries = (
            session.query(Injury)
            .filter_by(club_id=club_id, is_active=True)
            .count()
        )

        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()
        squad = session.query(Player).filter_by(club_id=club_id).all()
        available = [p for p in squad if (p.injured_weeks or 0) == 0]

        # 3+ injuries: injury crisis
        if active_injuries >= 3:
            for p in available:
                p.fitness = clamp((p.fitness or 100) - 5, 0.0, 100.0)
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=f"Injury crisis deepens at {club.name}",
                body=f"{club.name} now have {active_injuries} players in the treatment room. "
                     f"The remaining squad face increased workload.",
                category="injury",
            ))
            effects.append(f"{club.name}: Injury crisis — {active_injuries} injuries, squad fatigue +5")

        # 5+ injuries: injury epidemic
        if active_injuries >= 5:
            if board is not None:
                board.board_confidence = clamp(board.board_confidence - 3, 0.0, 100.0)

            # Extra recovery time for low medical facilities
            medical_level = club.medical_facility_level or 5
            if medical_level < 7:
                active_injury_records = (
                    session.query(Injury)
                    .filter_by(club_id=club_id, is_active=True)
                    .all()
                )
                for inj in active_injury_records:
                    inj.recovery_weeks_remaining = (inj.recovery_weeks_remaining or 0) + 1
                effects.append(f"{club.name}: Poor medical facilities — recovery +1 week for all injuries")

            effects.append(f"{club.name}: Injury epidemic — board confidence -3")

        # Re-injury tracking
        injured_player = session.get(Player, injured_player_id)
        if injured_player is not None:
            same_type_count = (
                session.query(Injury)
                .filter_by(player_id=injured_player_id, injury_type=injury_type)
                .count()
            )
            if same_type_count >= 2:
                injured_player.injury_proneness = min(
                    (injured_player.injury_proneness or 30) + 5, 99
                )
                effects.append(
                    f"{injured_player.name}: Recurring {injury_type} — injury_proneness +5"
                )
                # Find active injury and extend recovery
                active_inj = (
                    session.query(Injury)
                    .filter_by(player_id=injured_player_id, is_active=True)
                    .order_by(Injury.id.desc())
                    .first()
                )
                if active_inj:
                    extra = max(1, int((active_inj.recovery_weeks_remaining or 1) * 0.2))
                    active_inj.recovery_weeks_remaining = (
                        (active_inj.recovery_weeks_remaining or 1) + extra
                    )

            if same_type_count >= 3 and injured_player.potential:
                injured_player.potential = max(1, injured_player.potential - 3)
                effects.append(
                    f"{injured_player.name}: 3rd {injury_type} — permanent damage, potential -3"
                )

        # Key player injury ripple
        if injured_player and (injured_player.overall or 0) >= 80:
            pos = injured_player.position
            replacements = [
                p for p in available
                if p.id != injured_player_id
                and (p.position == pos
                     or (p.secondary_positions and pos in (p.secondary_positions or "")))
            ]
            if replacements:
                best_replacement = max(replacements, key=lambda p: p.overall or 0)
                # "Big shoes to fill" pressure
                best_replacement.composure = max(
                    1, (best_replacement.composure or 50) - 5
                )
                effects.append(
                    f"{best_replacement.name}: Big shoes to fill replacing {injured_player.name}"
                )
            else:
                # No adequate replacement — tactical vulnerability
                effects.append(
                    f"{club.name}: No adequate replacement for {injured_player.name} — tactical vulnerability"
                )

        if effects:
            _log(session, season, matchday, "injury_cascade", "club", club_id,
                 "; ".join(effects), float(-active_injuries))

        return effects


# ── System 4: Financial Pressure Spiral ─────────────────────────────────────


class FinancialPressure:
    """Models financial distress and its cascading consequences."""

    @staticmethod
    def process_financial_state(session: Session, club_id: int, season: int, matchday: int) -> list[str]:
        """Run weekly. Checks financial health and triggers consequences.

        Returns list of effect descriptions.
        """
        effects: list[str] = []
        club = session.get(Club, club_id)
        if club is None:
            return effects

        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()
        squad = session.query(Player).filter_by(club_id=club_id).all()

        total_wages = club.total_wages or 0
        wage_budget = club.wage_budget or 0

        if total_wages <= 0 or wage_budget <= 0:
            return effects

        ratio = total_wages / wage_budget

        # > 90% wage ratio: financial strain
        if ratio > 0.9:
            if board is not None:
                board.board_confidence = clamp(board.board_confidence - 2, 0.0, 100.0)
            effects.append(
                f"{club.name}: Financial strain — wage ratio {ratio:.0%}, no new signings recommended"
            )

        # > 100% wage ratio: financial crisis
        if ratio > 1.0:
            # Force sale of highest-paid non-essential player
            non_essential = [
                p for p in squad
                if (p.squad_role or "not_set") in ("rotation", "backup", "youth", "not_set")
            ]
            if non_essential:
                highest_paid = max(non_essential, key=lambda p: p.wage or 0)
                highest_paid.wants_transfer = True
                if highest_paid.market_value:
                    highest_paid.release_clause = highest_paid.market_value * 0.8
                effects.append(
                    f"{club.name}: Financial crisis — {highest_paid.name} listed for sale"
                )

            # Staff wage cut rumour: morale hit
            for p in squad:
                p.morale = clamp(p.morale - 2, 0.0, 100.0)

            # Youth academy funding cut
            if club.youth_academy_level and club.youth_academy_level > 1:
                club.youth_academy_level = max(1, club.youth_academy_level - 1)
                effects.append(f"{club.name}: Youth academy funding cut")

        # Negative budget: insolvency threat
        if (club.budget or 0) < 0:
            # Chance of points deduction
            if random.random() < 0.05:
                standing = (
                    session.query(LeagueStanding)
                    .filter_by(club_id=club_id, season=season)
                    .first()
                )
                if standing:
                    standing.points = max(0, (standing.points or 0) - 3)
                    session.add(NewsItem(
                        season=season, matchday=matchday,
                        headline=f"{club.name} docked 3 points for financial irregularities",
                        body=f"The league has deducted 3 points from {club.name} "
                             f"due to ongoing financial difficulties.",
                        category="finance",
                    ))
                    effects.append(f"{club.name}: 3 points deducted")

            if board is not None:
                board.fan_happiness = clamp(board.fan_happiness - 5, 0.0, 100.0)

            effects.append(f"{club.name}: Insolvency threat — budget negative")

        # Revenue anticipation based on standing
        standing = (
            session.query(LeagueStanding)
            .filter_by(club_id=club_id, season=season)
            .first()
        )
        if standing and club.league_id:
            from fm.db.models import League
            league = session.get(League, club.league_id)
            if league:
                all_standings = (
                    session.query(LeagueStanding)
                    .filter_by(league_id=club.league_id, season=season)
                    .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
                    .all()
                )
                position = next(
                    (i + 1 for i, s in enumerate(all_standings) if s.club_id == club_id),
                    len(all_standings),
                )
                # Top 4 anticipation
                if position <= 4 and matchday > 10:
                    club.budget = (club.budget or 0) + (club.budget or 0) * 0.001
                    effects.append(f"{club.name}: European qualification anticipated — small budget boost")

                # Relegation zone sponsor pressure
                num_teams = league.num_teams or 20
                relegation_zone = num_teams - (league.relegation_spots or 3) + 1
                if position >= relegation_zone and matchday > 15:
                    effects.append(f"{club.name}: Relegation threat — sponsors nervous")

        if effects:
            _log(session, season, matchday, "financial_pressure", "club", club_id,
                 "; ".join(effects), -ratio if ratio > 0.9 else 0.0)

        return effects


# ── System 5: Manager Trust & Job Security ──────────────────────────────────


class ManagerJobSecurity:
    """Models manager trust erosion and sacking probability."""

    @staticmethod
    def calculate_sacking_probability(session: Session, club_id: int, season: int) -> float:
        """Returns 0.0-1.0 probability of being sacked this matchday."""
        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()
        if board is None:
            return 0.0

        confidence = board.board_confidence or 60

        # Base probability from board confidence
        if confidence > 50:
            prob = 0.0
        elif confidence > 30:
            prob = (50 - confidence) * 0.005  # 0-10%
        elif confidence > 10:
            prob = (30 - confidence) * 0.015  # 0-30%
        else:
            prob = 0.50 + (10 - confidence) * 0.05  # 50-100%

        # Fan unhappiness modifier
        fan_happiness = board.fan_happiness or 60
        if fan_happiness < 30:
            prob += 0.10

        # Losing streak modifier (check form)
        standing = (
            session.query(LeagueStanding)
            .filter_by(club_id=club_id, season=season)
            .first()
        )
        if standing:
            form_str = standing.form or ""
            losing_streak = 0
            for ch in reversed(form_str):
                if ch == "L":
                    losing_streak += 1
                else:
                    break
            if losing_streak >= 5:
                prob += 0.15

        # Ultimatum modifier
        if board.ultimatum_active:
            prob += 0.25

        # Transfer embargo modifier
        if board.transfer_embargo:
            prob += 0.05

        # Patience exhausted
        if (board.patience or 3) <= 0:
            prob += 0.20

        # Protection: first 10 matchdays (honeymoon)
        current_md = 0
        if standing:
            current_md = standing.played or 0
        if current_md <= 10:
            prob *= 0.5

        return clamp(prob, 0.0, 1.0)

    @staticmethod
    def process_sacking_check(
        session: Session, club_id: int, season: int, matchday: int,
        is_human: bool = False,
    ) -> bool:
        """Run after each match. May trigger sacking for AI clubs.

        Returns True if the manager was sacked.
        """
        if is_human:
            # Human managers don't get auto-sacked, but we record the pressure
            return False

        prob = ManagerJobSecurity.calculate_sacking_probability(session, club_id, season)

        if random.random() >= prob:
            return False

        # SACKED!
        club = session.get(Club, club_id)
        club_name = club.name if club else f"Club#{club_id}"

        session.add(NewsItem(
            season=season, matchday=matchday,
            headline=f"Manager sacked at {club_name} after poor run",
            body=f"The board at {club_name} have lost patience and dismissed "
                 f"the manager following a poor run of results.",
            category="manager",
        ))

        # Reset board confidence to 50 (new manager bounce)
        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()
        if board:
            board.board_confidence = 50.0
            board.ultimatum_active = False
            board.warnings_issued = 0

        # Temporary morale boost
        squad = session.query(Player).filter_by(club_id=club_id).all()
        for p in squad:
            p.morale = clamp(p.morale + 5, 0.0, 100.0)
            p.trust_in_manager = 50.0  # reset trust for new manager

        # Assign new random tactical style to AI manager
        from fm.db.models import Manager
        manager = session.query(Manager).filter_by(club_id=club_id).first()
        if manager:
            styles = ["attacking", "balanced", "defensive", "possession", "counter_attack"]
            manager.tactical_style = random.choice(styles)

        _log(session, season, matchday, "manager_sacked", "club", club_id,
             f"Manager sacked at {club_name} (prob={prob:.2f})", -50.0)

        return True


# ── System 6: Comeback & Underdog Narratives ───────────────────────────────


class CascadingNarrativeEngine:
    """Generates and tracks multi-matchday narrative arcs.

    Named CascadingNarrativeEngine to avoid collision with the existing
    ``fm.world.news_engine.NarrativeEngine``.
    """

    NARRATIVE_TYPES = {
        "underdog_run": "Club performing 10+ positions above expectation",
        "title_race": "Within 5 points of leader with 10+ matchdays remaining",
        "relegation_battle": "Within 3 points of relegation zone",
        "injury_crisis": "3+ first-team players injured simultaneously",
        "youth_breakthrough": "Player under 21 scored 3+ goals in 5 matches",
        "redemption_arc": "Team wins 3 after losing 3 (form reversal)",
        "unbeaten_run": "8+ matches without defeat",
        "manager_under_pressure": "Board confidence < 30",
    }

    @staticmethod
    def detect_narratives(session: Session, club_id: int, season: int, matchday: int) -> list[str]:
        """Detect active narrative arcs, apply their effects, and return names."""
        narratives: list[str] = []

        club = session.get(Club, club_id)
        if club is None:
            return narratives

        board = session.query(BoardExpectation).filter_by(club_id=club_id).first()
        squad = session.query(Player).filter_by(club_id=club_id).all()
        standing = (
            session.query(LeagueStanding)
            .filter_by(club_id=club_id, season=season)
            .first()
        )

        # ── underdog_run ──
        if standing and board and club.league_id:
            all_standings = (
                session.query(LeagueStanding)
                .filter_by(league_id=club.league_id, season=season)
                .order_by(LeagueStanding.points.desc(), LeagueStanding.goal_difference.desc())
                .all()
            )
            position = next(
                (i + 1 for i, s in enumerate(all_standings) if s.club_id == club_id),
                len(all_standings),
            )
            expected_pos = (board.min_league_position + board.max_league_position) // 2
            if expected_pos - position >= 10:
                narratives.append("underdog_run")
                for p in squad:
                    p.morale = clamp(p.morale + 3, 0.0, 100.0)
                    p.composure = min(99, (p.composure or 50) + 1)

            # ── title_race ──
            if all_standings and position <= 4:
                leader_pts = all_standings[0].points or 0
                my_pts = standing.points or 0
                from fm.db.models import League
                league = session.get(League, club.league_id)
                total_matchdays = ((league.num_teams or 20) - 1) * 2 if league else 38
                remaining = total_matchdays - matchday
                if leader_pts - my_pts <= 5 and remaining >= 10 and position > 1:
                    narratives.append("title_race")
                    for p in squad:
                        p.morale = clamp(p.morale + 2, 0.0, 100.0)

            # ── relegation_battle ──
            if all_standings:
                from fm.db.models import League
                league = session.get(League, club.league_id)
                num_teams = league.num_teams if league else 20
                relegation_line = num_teams - (league.relegation_spots if league else 3)
                if relegation_line < len(all_standings):
                    safe_pts = all_standings[relegation_line].points or 0
                    my_pts = standing.points or 0
                    if my_pts - safe_pts <= 3 and position > relegation_line:
                        narratives.append("relegation_battle")
                        for p in squad:
                            p.morale = clamp(p.morale - 2, 0.0, 100.0)
                            p.determination = min(99, (p.determination or 50) + 1)

        # ── injury_crisis ──
        active_injuries = (
            session.query(Injury).filter_by(club_id=club_id, is_active=True).count()
        )
        if active_injuries >= 3:
            narratives.append("injury_crisis")
            for p in squad:
                p.morale = clamp(p.morale - 3, 0.0, 100.0)

        # ── youth_breakthrough ──
        youth_stars = [
            p for p in squad
            if (p.age or 30) < 21 and (p.goals_season or 0) >= 3
        ]
        if youth_stars:
            narratives.append("youth_breakthrough")
            for p in youth_stars:
                p.morale = clamp(p.morale + 5, 0.0, 100.0)
            for p in squad:
                p.morale = clamp(p.morale + 2, 0.0, 100.0)

        # ── redemption_arc ──
        if standing:
            form_str = standing.form or ""
            if len(form_str) >= 6:
                last6 = form_str[-6:]
                # Check for LLL followed by WWW
                if last6[:3] == "LLL" and last6[3:] == "WWW":
                    narratives.append("redemption_arc")
                    for p in squad:
                        p.morale = clamp(p.morale + 5, 0.0, 100.0)
                    if p:
                        p.composure = min(99, (p.composure or 50) + 1)

        # ── unbeaten_run ──
        if standing:
            form_str = standing.form or ""
            unbeaten_count = 0
            for ch in reversed(form_str):
                if ch in ("W", "D"):
                    unbeaten_count += 1
                else:
                    break
            if unbeaten_count >= 8:
                narratives.append("unbeaten_run")
                for p in squad:
                    p.morale = clamp(p.morale + 3, 0.0, 100.0)

        # ── manager_under_pressure ──
        if board and (board.board_confidence or 60) < 30:
            narratives.append("manager_under_pressure")
            for p in squad:
                p.morale = clamp(p.morale - 3, 0.0, 100.0)

        return narratives

    @staticmethod
    def generate_matchday_news(
        session: Session, club_id: int, season: int, matchday: int,
        narratives: list[str],
    ) -> None:
        """Create :class:`NewsItem` entries from active narratives."""
        club = session.get(Club, club_id)
        club_name = club.name if club else f"Club#{club_id}"

        _HEADLINES: dict[str, list[str]] = {
            "underdog_run": [
                f"Fairy tale continues for {club_name}",
                f"Against all odds: {club_name}'s remarkable season",
                f"{club_name} defy expectations once again",
            ],
            "title_race": [
                f"Title race heats up as {club_name} stay in contention",
                f"{club_name} keep pressure on league leaders",
                f"Can {club_name} pull off the impossible?",
            ],
            "relegation_battle": [
                f"{club_name} in relegation dogfight",
                f"Survival battle intensifies for {club_name}",
                f"Anxious times at {club_name} as drop zone looms",
            ],
            "injury_crisis": [
                f"Injury-hit {club_name} face tough test",
                f"Medical crisis deepens at {club_name}",
                f"{club_name} squad decimated by injuries",
            ],
            "youth_breakthrough": [
                f"Academy star shines at {club_name}",
                f"Youth revolution taking hold at {club_name}",
                f"Future is bright for {club_name}'s young guns",
            ],
            "redemption_arc": [
                f"The comeback kings: {club_name}'s incredible turnaround",
                f"{club_name} rise from the ashes",
                f"From despair to delight for {club_name}",
            ],
            "unbeaten_run": [
                f"{club_name}'s unbeaten run shows no signs of stopping",
                f"Fortress mentality at {club_name}",
                f"Nobody can stop {club_name} right now",
            ],
            "manager_under_pressure": [
                f"Pressure mounts on {club_name} boss",
                f"Dark clouds gathering over {club_name} dugout",
                f"How long can the {club_name} manager survive?",
            ],
        }

        for narrative in narratives:
            templates = _HEADLINES.get(narrative, [f"Story developing at {club_name}"])
            headline = random.choice(templates)
            body = CascadingNarrativeEngine.NARRATIVE_TYPES.get(
                narrative, "An emerging storyline."
            )
            session.add(NewsItem(
                season=season, matchday=matchday,
                headline=headline,
                body=f"{headline}. {body}",
                category="general",
            ))


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
