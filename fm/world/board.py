"""Board expectations, confidence, sacking risk, and fan management.

The board sets season objectives based on club reputation and squad
strength, evaluates the manager throughout the season, and can issue
warnings or sack the manager.  Fans react to results, style of play,
and transfers, affecting attendance and home advantage.
"""
from __future__ import annotations

import enum
import random
import math
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from fm.db.models import (
    Club, Player, League, LeagueStanding, Fixture, Season, NewsItem,
)
from fm.config import STARTING_SEASON


# ── Enums ─────────────────────────────────────────────────────────────────

class BoardType(str, enum.Enum):
    SUGAR_DADDY = "sugar_daddy"   # high patience, big budget
    BALANCED = "balanced"          # moderate patience and budget
    FRUGAL = "frugal"             # low budget but patient
    SELLING = "selling"           # sell stars, develop youth


class ExpectationLevel(str, enum.Enum):
    WIN_LEAGUE = "win_league"
    TITLE_CHALLENGE = "title_challenge"
    TOP_FOUR = "top_four"
    TOP_HALF = "top_half"
    MID_TABLE = "mid_table"
    AVOID_RELEGATION = "avoid_relegation"
    SURVIVE = "survive"


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class BoardExpectation:
    """What the board expects for this season."""
    club_id: int
    season: int
    league_target: ExpectationLevel
    cup_target: str  # "win", "semi_final", "quarter_final", "progress", "no_expectation"
    budget_stance: str  # "generous", "moderate", "tight"
    youth_focus: bool  # board wants youth development
    net_spend_limit: float  # millions, negative = must sell


@dataclass
class BoardState:
    """Persistent board tracking for a club across one season."""
    club_id: int
    board_type: BoardType
    confidence: float = 50.0      # 0-100
    patience: float = 50.0        # 0-100 (higher = more forgiving)
    warning_issued: bool = False
    warning_matchday: int = 0
    matches_below_threshold: int = 0
    season_started: bool = False


@dataclass
class FanState:
    """Fan mood tracking for a club."""
    club_id: int
    happiness: float = 60.0       # 0-100
    excitement: float = 50.0      # 0-100 (big wins, signings)
    loyalty: float = 70.0         # 0-100 (slow-moving, legacy fans)
    recent_attendance_pct: float = 0.85  # fraction of capacity


# ── In-memory state stores ────────────────────────────────────────────────

_board_states: dict[int, BoardState] = {}         # club_id -> state
_board_expectations: dict[int, BoardExpectation] = {}  # club_id -> expectation
_fan_states: dict[int, FanState] = {}             # club_id -> fan state


# ── Board messages ────────────────────────────────────────────────────────

_BOARD_MESSAGES_POSITIVE = [
    "The board is delighted with recent results and fully backs the manager.",
    "Board confidence is high. Keep up the excellent work.",
    "The chairman has praised the manager's performance in the media.",
    "The board is pleased with the direction of the club.",
    "Shareholders are happy with the club's progress this season.",
]

_BOARD_MESSAGES_NEUTRAL = [
    "The board is monitoring results but remains patient.",
    "The board expects an improvement in upcoming fixtures.",
    "The chairman has expressed cautious optimism about the season.",
    "The board acknowledges some mixed results but is not yet concerned.",
    "The board wants to see more consistency going forward.",
]

_BOARD_MESSAGES_NEGATIVE = [
    "The board is growing concerned about recent performances.",
    "Rumours suggest the board is losing patience with the manager.",
    "The chairman has demanded an immediate improvement in results.",
    "Board confidence is low. The manager's position is under scrutiny.",
    "Sources close to the board indicate the manager is on thin ice.",
]

_BOARD_MESSAGES_CRITICAL = [
    "The board has issued a formal warning. Results must improve immediately.",
    "The manager's position is hanging by a thread.",
    "Board members are actively discussing the manager's future.",
    "An emergency board meeting has been called to discuss the manager.",
    "The board has given the manager a final chance to turn things around.",
]


# ══════════════════════════════════════════════════════════════════════════
#  BoardManager
# ══════════════════════════════════════════════════════════════════════════

class BoardManager:
    """Manages board expectations, confidence, warnings, and sacking risk."""

    def __init__(self, session: Session):
        self.session = session

    # ── Setup & expectations ──────────────────────────────────────────────

    def initialise_board(self, club_id: int, board_type: BoardType | None = None):
        """Set up the board state for a club. Called at start of game."""
        club = self.session.query(Club).get(club_id)
        if not club:
            return

        if board_type is None:
            board_type = self._infer_board_type(club)

        patience = {
            BoardType.SUGAR_DADDY: random.uniform(60, 80),
            BoardType.BALANCED: random.uniform(40, 60),
            BoardType.FRUGAL: random.uniform(50, 70),
            BoardType.SELLING: random.uniform(45, 65),
        }[board_type]

        state = BoardState(
            club_id=club_id,
            board_type=board_type,
            confidence=55.0 + random.uniform(-5, 10),
            patience=patience,
        )
        _board_states[club_id] = state

    def set_expectations(self, club_id: int, season: int):
        """Auto-set board expectations based on reputation and squad."""
        club = self.session.query(Club).get(club_id)
        if not club:
            return

        state = _board_states.get(club_id)
        if not state:
            self.initialise_board(club_id)
            state = _board_states[club_id]

        rep = club.reputation or 50
        league = self.session.query(League).get(club.league_id) if club.league_id else None
        tier = league.tier if league else 1

        # Squad strength
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        avg_ovr = (
            sum(p.overall or 50 for p in players) / max(len(players), 1)
            if players else 50
        )

        # Combined score for target calculation
        score = rep * 0.6 + avg_ovr * 0.4

        if tier == 1:
            if score >= 80:
                league_target = ExpectationLevel.WIN_LEAGUE
            elif score >= 72:
                league_target = ExpectationLevel.TITLE_CHALLENGE
            elif score >= 64:
                league_target = ExpectationLevel.TOP_FOUR
            elif score >= 55:
                league_target = ExpectationLevel.TOP_HALF
            elif score >= 45:
                league_target = ExpectationLevel.MID_TABLE
            else:
                league_target = ExpectationLevel.AVOID_RELEGATION
        else:
            # Lower divisions: expectations scaled down
            if score >= 70:
                league_target = ExpectationLevel.WIN_LEAGUE
            elif score >= 60:
                league_target = ExpectationLevel.TITLE_CHALLENGE
            elif score >= 50:
                league_target = ExpectationLevel.TOP_HALF
            else:
                league_target = ExpectationLevel.AVOID_RELEGATION

        # Cup target
        if score >= 75:
            cup_target = "semi_final"
        elif score >= 60:
            cup_target = "quarter_final"
        elif score >= 45:
            cup_target = "progress"
        else:
            cup_target = "no_expectation"

        # Budget stance
        budget_stance = {
            BoardType.SUGAR_DADDY: "generous",
            BoardType.BALANCED: "moderate",
            BoardType.FRUGAL: "tight",
            BoardType.SELLING: "tight",
        }[state.board_type]

        # Net spend limit
        net_spend = {
            BoardType.SUGAR_DADDY: (club.budget or 0) * 0.8,
            BoardType.BALANCED: (club.budget or 0) * 0.5,
            BoardType.FRUGAL: (club.budget or 0) * 0.25,
            BoardType.SELLING: -(club.budget or 0) * 0.1,  # must generate profit
        }[state.board_type]

        youth_focus = state.board_type == BoardType.SELLING

        expectation = BoardExpectation(
            club_id=club_id,
            season=season,
            league_target=league_target,
            cup_target=cup_target,
            budget_stance=budget_stance,
            youth_focus=youth_focus,
            net_spend_limit=round(net_spend, 1),
        )
        _board_expectations[club_id] = expectation

        state.season_started = True
        state.confidence = 55.0 + random.uniform(-5, 10)
        state.warning_issued = False
        state.matches_below_threshold = 0

    def get_expectations(self, club_id: int) -> BoardExpectation | None:
        """Return the current board expectations for a club."""
        return _board_expectations.get(club_id)

    # ── Match-by-match evaluation ─────────────────────────────────────────

    def evaluate_manager_performance(self, club_id: int) -> dict:
        """Evaluate current manager performance against expectations.

        Returns a dict with confidence, status label, and detail breakdown.
        """
        state = _board_states.get(club_id)
        expectation = _board_expectations.get(club_id)
        if not state or not expectation:
            return {"confidence": 50.0, "status": "Unknown", "detail": {}}

        club = self.session.query(Club).get(club_id)
        season = self._current_season()

        # Get current league position
        standing = self.session.query(LeagueStanding).filter_by(
            club_id=club_id, season=season.year
        ).first()

        all_standings = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=club.league_id, season=season.year)
            .order_by(LeagueStanding.points.desc(),
                      LeagueStanding.goal_difference.desc())
            .all()
        ) if club and club.league_id else []

        position = 1
        for i, st in enumerate(all_standings):
            if st.club_id == club_id:
                position = i + 1
                break

        total_teams = len(all_standings) if all_standings else 20

        # Calculate performance vs target
        target_pos = _expectation_to_position(expectation.league_target, total_teams)
        pos_diff = target_pos - position  # positive = ahead of expectations

        # Form analysis
        form_str = standing.form if standing else ""
        recent_wins = form_str.count("W")
        recent_losses = form_str.count("L")
        form_score = (recent_wins - recent_losses) * 5  # -25 to +25

        # Points per game analysis
        ppg = 0.0
        if standing and standing.played and standing.played > 0:
            ppg = standing.points / standing.played

        target_ppg = _target_ppg(expectation.league_target)
        ppg_diff = ppg - target_ppg

        return {
            "confidence": round(state.confidence, 1),
            "status": _confidence_label(state.confidence),
            "warning_issued": state.warning_issued,
            "position": position,
            "target_position": target_pos,
            "position_vs_target": pos_diff,
            "form_score": form_score,
            "ppg": round(ppg, 2),
            "target_ppg": target_ppg,
            "board_type": state.board_type.value,
            "patience": round(state.patience, 1),
            "detail": {
                "league_target": expectation.league_target.value,
                "cup_target": expectation.cup_target,
                "budget_stance": expectation.budget_stance,
            },
        }

    def process_matchday_board_reaction(
        self, club_id: int, goals_for: int, goals_against: int,
        opponent_reputation: int = 50, was_home: bool = True
    ):
        """Update board confidence after a match result."""
        state = _board_states.get(club_id)
        expectation = _board_expectations.get(club_id)
        if not state or not expectation:
            return

        club = self.session.query(Club).get(club_id)
        if not club:
            return

        goal_diff = goals_for - goals_against
        club_rep = club.reputation or 50
        opp_rep = opponent_reputation

        # Base confidence change from result
        if goal_diff > 0:
            # Win
            base_change = 3.0 + min(goal_diff, 4) * 0.8
            # Bonus for beating stronger teams
            if opp_rep > club_rep + 10:
                base_change += (opp_rep - club_rep) * 0.1
            # Reduced for beating much weaker teams
            elif opp_rep < club_rep - 20:
                base_change *= 0.5
        elif goal_diff == 0:
            # Draw
            if opp_rep > club_rep + 15:
                base_change = 1.0  # Decent draw
            elif opp_rep < club_rep - 15:
                base_change = -2.5  # Should have won
            else:
                base_change = -0.5
        else:
            # Loss
            base_change = -4.0 - min(abs(goal_diff), 4) * 1.0
            # Worse for losing to weaker teams
            if opp_rep < club_rep - 10:
                base_change -= (club_rep - opp_rep) * 0.08
            # Less bad for losing to much stronger teams
            elif opp_rep > club_rep + 20:
                base_change *= 0.5
            # Home loss stings more
            if was_home:
                base_change -= 1.0

        # Apply patience modifier (more patient boards react less to single results)
        patience_mod = 1.0 - (state.patience / 200.0)  # 0.6 to 0.8 range
        base_change *= patience_mod

        # Random variation
        base_change += random.uniform(-1.0, 1.0)

        state.confidence = max(0.0, min(100.0, state.confidence + base_change))

        # Track consecutive poor results
        if goal_diff < 0:
            state.matches_below_threshold += 1
        elif goal_diff > 0:
            state.matches_below_threshold = max(0, state.matches_below_threshold - 1)

        # Check for warning
        if state.confidence < 25 and not state.warning_issued:
            state.warning_issued = True
            season = self._current_season()
            state.warning_matchday = season.current_matchday or 0

            self.session.add(NewsItem(
                season=season.year,
                matchday=season.current_matchday,
                headline=f"{club.name} board issues warning to manager",
                body=f"The board at {club.name} have issued a formal warning. "
                     f"Results must improve or the manager faces the sack.",
                category="manager",
            ))
            self.session.flush()

        # Recovery: if confidence goes back up, clear warning
        if state.warning_issued and state.confidence > 40:
            state.warning_issued = False
            state.matches_below_threshold = 0

    def check_sacking_risk(self, club_id: int) -> float:
        """Return sacking probability (0.0 to 1.0).

        Sacking happens when confidence stays critically low for multiple
        matchdays.  Patient boards tolerate more.
        """
        state = _board_states.get(club_id)
        if not state:
            return 0.0

        if state.confidence >= 20:
            return 0.0

        if not state.warning_issued:
            return 0.0

        # How long since warning
        season = self._current_season()
        md_since_warning = (season.current_matchday or 0) - state.warning_matchday

        if md_since_warning < 3:
            return 0.0  # Grace period

        # Base sacking probability
        prob = 0.0
        if state.confidence < 10:
            prob = 0.3 + (10 - state.confidence) * 0.05
        elif state.confidence < 15:
            prob = 0.15
        elif state.confidence < 20:
            prob = 0.05

        # Patience reduces probability
        patience_factor = state.patience / 100.0
        prob *= (1.0 - patience_factor * 0.5)

        # Consecutive poor results increase probability
        if state.matches_below_threshold >= 5:
            prob += 0.15
        elif state.matches_below_threshold >= 3:
            prob += 0.08

        return min(1.0, max(0.0, prob))

    def process_sacking_check(self, club_id: int) -> bool:
        """Roll the dice on whether the manager gets sacked.

        Returns True if sacked.
        """
        risk = self.check_sacking_risk(club_id)
        if risk <= 0:
            return False

        if random.random() < risk:
            club = self.session.query(Club).get(club_id)
            season = self._current_season()
            if club:
                self.session.add(NewsItem(
                    season=season.year,
                    matchday=season.current_matchday,
                    headline=f"{club.name} sack their manager!",
                    body=f"After a dismal run of results, the board at {club.name} "
                         f"have decided to part ways with the manager.",
                    category="manager",
                ))
                self.session.flush()
            return True
        return False

    # ── Budget requests ───────────────────────────────────────────────────

    def request_budget_increase(self, club_id: int) -> dict:
        """Request additional transfer budget from the board.

        Returns dict with success, amount, and message.
        """
        state = _board_states.get(club_id)
        club = self.session.query(Club).get(club_id)
        if not state or not club:
            return {"success": False, "amount": 0, "message": "No board data."}

        # Chance depends on confidence and board type
        base_chance = state.confidence / 100.0

        type_modifier = {
            BoardType.SUGAR_DADDY: 0.3,
            BoardType.BALANCED: 0.1,
            BoardType.FRUGAL: -0.1,
            BoardType.SELLING: -0.2,
        }[state.board_type]

        chance = max(0.05, min(0.9, base_chance + type_modifier))

        if random.random() < chance:
            # Determine amount
            base_amount = (club.budget or 0) * random.uniform(0.1, 0.3)
            amount_multiplier = {
                BoardType.SUGAR_DADDY: 2.0,
                BoardType.BALANCED: 1.0,
                BoardType.FRUGAL: 0.5,
                BoardType.SELLING: 0.3,
            }[state.board_type]

            amount = max(0.5, base_amount * amount_multiplier)
            club.budget = (club.budget or 0) + amount

            season = self._current_season()
            self.session.add(NewsItem(
                season=season.year,
                matchday=season.current_matchday,
                headline=f"{club.name} board release extra funds",
                body=f"The board have approved an additional {amount:.1f}M "
                     f"for the transfer budget.",
                category="finance",
            ))
            self.session.flush()

            return {
                "success": True,
                "amount": round(amount, 1),
                "message": f"The board has approved an extra {amount:.1f}M for transfers.",
            }
        else:
            # Confidence drops slightly from failed request
            state.confidence = max(0.0, state.confidence - 2.0)
            return {
                "success": False,
                "amount": 0,
                "message": "The board has rejected your request for additional funds.",
            }

    def request_staff_hiring(self, club_id: int) -> dict:
        """Request to hire additional coaching staff.

        Returns dict with success and message.
        """
        state = _board_states.get(club_id)
        club = self.session.query(Club).get(club_id)
        if not state or not club:
            return {"success": False, "message": "No board data."}

        chance = (state.confidence / 100.0) * 0.6 + 0.2
        if state.board_type == BoardType.FRUGAL:
            chance *= 0.6

        if random.random() < chance:
            # Improve facilities as a proxy for better staff
            club.facilities_level = min(10, (club.facilities_level or 5) + 1)
            cost = (club.facilities_level or 5) * 0.3
            club.budget = (club.budget or 0) - cost

            self.session.flush()
            return {
                "success": True,
                "message": f"The board has approved hiring new coaching staff. "
                           f"Facilities improved to level {club.facilities_level}.",
            }
        else:
            return {
                "success": False,
                "message": "The board doesn't feel additional staff is needed right now.",
            }

    # ── End of season ─────────────────────────────────────────────────────

    def process_end_of_season_review(self, club_id: int, season_year: int) -> dict:
        """End-of-season board review.

        Compares actual performance against expectations and adjusts
        confidence for the next season.
        """
        state = _board_states.get(club_id)
        expectation = _board_expectations.get(club_id)
        if not state or not expectation:
            return {"verdict": "Unknown", "confidence_change": 0}

        club = self.session.query(Club).get(club_id)
        if not club:
            return {"verdict": "Unknown", "confidence_change": 0}

        # Get final position
        all_standings = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=club.league_id, season=season_year)
            .order_by(LeagueStanding.points.desc(),
                      LeagueStanding.goal_difference.desc())
            .all()
        ) if club.league_id else []

        position = 1
        for i, st in enumerate(all_standings):
            if st.club_id == club_id:
                position = i + 1
                break

        total_teams = len(all_standings) if all_standings else 20
        target_pos = _expectation_to_position(expectation.league_target, total_teams)

        pos_diff = target_pos - position  # positive = exceeded expectations

        # Verdict
        if pos_diff >= 5:
            verdict = "Exceptional"
            conf_change = random.uniform(15, 25)
        elif pos_diff >= 2:
            verdict = "Exceeded expectations"
            conf_change = random.uniform(8, 15)
        elif pos_diff >= 0:
            verdict = "Met expectations"
            conf_change = random.uniform(2, 8)
        elif pos_diff >= -3:
            verdict = "Slightly disappointing"
            conf_change = random.uniform(-8, -2)
        elif pos_diff >= -6:
            verdict = "Disappointing"
            conf_change = random.uniform(-15, -8)
        else:
            verdict = "Disastrous"
            conf_change = random.uniform(-25, -15)

        state.confidence = max(0.0, min(100.0, state.confidence + conf_change))

        season = self._current_season()
        self.session.add(NewsItem(
            season=season_year,
            headline=f"{club.name} board's season verdict: {verdict}",
            body=f"The board at {club.name} have rated the season as '{verdict}'. "
                 f"Finished {_ordinal(position)} (target: {_ordinal(target_pos)}).",
            category="manager",
        ))
        self.session.flush()

        return {
            "verdict": verdict,
            "confidence_change": round(conf_change, 1),
            "final_confidence": round(state.confidence, 1),
            "position": position,
            "target_position": target_pos,
        }

    # ── Messages ──────────────────────────────────────────────────────────

    def get_board_message(self, club_id: int) -> str:
        """Return a contextual board message for the current state."""
        state = _board_states.get(club_id)
        if not state:
            return "The board has no comment at this time."

        conf = state.confidence
        if conf >= 70:
            return random.choice(_BOARD_MESSAGES_POSITIVE)
        elif conf >= 40:
            return random.choice(_BOARD_MESSAGES_NEUTRAL)
        elif conf >= 20:
            return random.choice(_BOARD_MESSAGES_NEGATIVE)
        else:
            return random.choice(_BOARD_MESSAGES_CRITICAL)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _current_season(self) -> Season:
        return self.session.query(Season).order_by(Season.year.desc()).first()

    def _infer_board_type(self, club: Club) -> BoardType:
        """Guess board type from club characteristics."""
        rep = club.reputation or 50
        budget = club.budget or 0

        if budget > 100 and rep >= 75:
            return BoardType.SUGAR_DADDY
        elif rep < 40:
            return BoardType.SELLING
        elif budget < 10:
            return BoardType.FRUGAL
        else:
            return BoardType.BALANCED


# ══════════════════════════════════════════════════════════════════════════
#  FanManager
# ══════════════════════════════════════════════════════════════════════════

class FanManager:
    """Manages fan happiness, attendance, and stadium atmosphere."""

    def __init__(self, session: Session):
        self.session = session

    # ── Matchday processing ───────────────────────────────────────────────

    def process_matchday_fans(
        self, club_id: int, goals_for: int, goals_against: int,
        home_shots: int = 0, home_possession: float = 50.0,
        was_home: bool = True
    ):
        """Update fan mood after a match.

        Factors: result, style of play (shots, possession), margin of victory.
        """
        state = self._get_or_create_state(club_id)
        goal_diff = goals_for - goals_against

        # Result impact on happiness
        if goal_diff > 0:
            result_boost = 3.0 + min(goal_diff, 4) * 1.5
            if goal_diff >= 3:
                state.excitement = min(100.0, state.excitement + 8.0)
        elif goal_diff == 0:
            result_boost = -1.0
        else:
            result_boost = -4.0 - min(abs(goal_diff), 4) * 1.5
            if abs(goal_diff) >= 3:
                state.excitement = max(0.0, state.excitement - 5.0)

        # Home vs away modifier
        if was_home and goal_diff < 0:
            result_boost -= 2.0  # Fans hate losing at home
        elif not was_home and goal_diff > 0:
            result_boost += 1.5  # Away wins are appreciated

        # Style of play bonus (fans like attractive football)
        style_bonus = 0.0
        if home_shots >= 15:
            style_bonus += 1.5
        if home_possession >= 55:
            style_bonus += 1.0
        elif home_possession < 35:
            style_bonus -= 1.0

        # Apply to happiness
        total_change = result_boost + style_bonus + random.uniform(-1, 1)
        state.happiness = max(0.0, min(100.0, state.happiness + total_change))

        # Excitement decays slowly
        state.excitement = max(0.0, state.excitement - random.uniform(0.5, 2.0))

        # Loyalty is very slow-moving
        if goal_diff > 0:
            state.loyalty = min(100.0, state.loyalty + random.uniform(0.1, 0.5))
        elif goal_diff < 0:
            state.loyalty = max(0.0, state.loyalty - random.uniform(0.05, 0.2))

    def process_transfer_fan_reaction(
        self, club_id: int, player_name: str, player_overall: int,
        is_signing: bool, fee: float = 0.0
    ):
        """Fans react to transfers: big signings excite, losing stars angers."""
        state = self._get_or_create_state(club_id)

        if is_signing:
            # Excitement from signing
            if player_overall >= 80:
                state.excitement = min(100.0, state.excitement + 15.0)
                state.happiness = min(100.0, state.happiness + 5.0)
            elif player_overall >= 70:
                state.excitement = min(100.0, state.excitement + 8.0)
                state.happiness = min(100.0, state.happiness + 2.0)
            else:
                state.excitement = min(100.0, state.excitement + 2.0)

            # Overpaying annoys fans
            if fee > player_overall * 0.8:  # rough "overpay" check
                state.happiness = max(0.0, state.happiness - 3.0)
        else:
            # Selling a star
            if player_overall >= 80:
                state.happiness = max(0.0, state.happiness - 12.0)
                state.excitement = max(0.0, state.excitement - 8.0)

                season = self._current_season()
                club = self.session.query(Club).get(club_id)
                if club and season:
                    self.session.add(NewsItem(
                        season=season.year,
                        matchday=season.current_matchday,
                        headline=f"{club.name} fans furious over {player_name} sale",
                        body=f"Supporters of {club.name} are outraged by the decision "
                             f"to sell fan favourite {player_name}.",
                        category="general",
                    ))
                    self.session.flush()
            elif player_overall >= 70:
                state.happiness = max(0.0, state.happiness - 5.0)
            # Selling low-rated players barely matters

    def calculate_attendance(self, club_id: int, opponent_reputation: int = 50) -> int:
        """Calculate match attendance based on fan mood and opponent.

        Returns number of fans attending.
        """
        club = self.session.query(Club).get(club_id)
        if not club:
            return 0

        state = self._get_or_create_state(club_id)
        capacity = club.stadium_capacity or 30000

        # Base fill rate from happiness
        base_fill = 0.55 + (state.happiness / 100.0) * 0.35  # 0.55 to 0.90

        # Loyalty provides a floor
        loyalty_floor = 0.3 + (state.loyalty / 100.0) * 0.3  # 0.30 to 0.60
        base_fill = max(base_fill, loyalty_floor)

        # Big opponents attract more fans
        club_rep = club.reputation or 50
        if opponent_reputation > club_rep + 20:
            base_fill += 0.08  # Fans want to see the big team
        elif opponent_reputation > club_rep + 10:
            base_fill += 0.04

        # Excitement bonus (big signing, cup run, etc.)
        if state.excitement > 70:
            base_fill += 0.06
        elif state.excitement > 50:
            base_fill += 0.03

        # Season ticket holders guarantee minimum
        base_fill = max(0.35, base_fill)

        # Cap at 100%
        fill_rate = min(1.0, base_fill)

        # Apply some randomness (weather, day of week, etc.)
        fill_rate *= random.uniform(0.93, 1.02)
        fill_rate = max(0.25, min(1.0, fill_rate))

        state.recent_attendance_pct = fill_rate
        attendance = int(capacity * fill_rate)
        return attendance

    def get_fan_mood(self, club_id: int) -> dict:
        """Return fan mood summary."""
        state = self._get_or_create_state(club_id)
        return {
            "happiness": round(state.happiness, 1),
            "happiness_label": _fan_happiness_label(state.happiness),
            "excitement": round(state.excitement, 1),
            "loyalty": round(state.loyalty, 1),
            "recent_attendance_pct": round(state.recent_attendance_pct * 100, 1),
        }

    def get_stadium_atmosphere(self, club_id: int) -> float:
        """Return a 0.0-1.0 atmosphere score that affects home advantage.

        Full stadium + happy fans = loud atmosphere = bigger home boost.
        """
        state = self._get_or_create_state(club_id)

        # Attendance contribution (full stadium is louder)
        attendance_factor = state.recent_attendance_pct  # 0 to 1

        # Happiness contribution (happy fans sing louder)
        happiness_factor = state.happiness / 100.0

        # Excitement contribution (buzzing stadium)
        excitement_factor = state.excitement / 100.0

        atmosphere = (
            attendance_factor * 0.45 +
            happiness_factor * 0.35 +
            excitement_factor * 0.20
        )

        return max(0.0, min(1.0, atmosphere))

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_or_create_state(self, club_id: int) -> FanState:
        """Get or lazily create fan state for a club."""
        if club_id not in _fan_states:
            club = self.session.query(Club).get(club_id)
            rep = (club.reputation or 50) if club else 50

            # Initial fan state based on reputation
            _fan_states[club_id] = FanState(
                club_id=club_id,
                happiness=50.0 + rep * 0.2 + random.uniform(-5, 5),
                excitement=40.0 + random.uniform(-10, 10),
                loyalty=50.0 + rep * 0.3 + random.uniform(-5, 5),
                recent_attendance_pct=0.65 + rep * 0.003,
            )
        return _fan_states[club_id]

    def _current_season(self) -> Season:
        return self.session.query(Season).order_by(Season.year.desc()).first()


# ══════════════════════════════════════════════════════════════════════════
#  Module-level helpers
# ══════════════════════════════════════════════════════════════════════════

def _expectation_to_position(level: ExpectationLevel, total_teams: int) -> int:
    """Map an expectation level to an approximate league position."""
    return {
        ExpectationLevel.WIN_LEAGUE: 1,
        ExpectationLevel.TITLE_CHALLENGE: 2,
        ExpectationLevel.TOP_FOUR: 4,
        ExpectationLevel.TOP_HALF: max(1, total_teams // 2),
        ExpectationLevel.MID_TABLE: max(1, int(total_teams * 0.6)),
        ExpectationLevel.AVOID_RELEGATION: max(1, total_teams - 3),
        ExpectationLevel.SURVIVE: max(1, total_teams - 1),
    }[level]


def _target_ppg(level: ExpectationLevel) -> float:
    """Expected points per game for each target level."""
    return {
        ExpectationLevel.WIN_LEAGUE: 2.3,
        ExpectationLevel.TITLE_CHALLENGE: 2.1,
        ExpectationLevel.TOP_FOUR: 1.9,
        ExpectationLevel.TOP_HALF: 1.5,
        ExpectationLevel.MID_TABLE: 1.3,
        ExpectationLevel.AVOID_RELEGATION: 1.1,
        ExpectationLevel.SURVIVE: 1.0,
    }[level]


def _confidence_label(confidence: float) -> str:
    """Human-readable label for board confidence."""
    if confidence >= 80:
        return "Full support"
    elif confidence >= 60:
        return "Satisfied"
    elif confidence >= 40:
        return "Content"
    elif confidence >= 25:
        return "Concerned"
    elif confidence >= 15:
        return "Unhappy"
    return "Furious"


def _fan_happiness_label(happiness: float) -> str:
    """Human-readable label for fan happiness."""
    if happiness >= 85:
        return "Ecstatic"
    elif happiness >= 70:
        return "Happy"
    elif happiness >= 55:
        return "Content"
    elif happiness >= 40:
        return "Frustrated"
    elif happiness >= 25:
        return "Angry"
    return "Hostile"


def _ordinal(n: int) -> str:
    """Return ordinal string for a number (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
