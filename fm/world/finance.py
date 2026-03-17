"""Comprehensive financial simulation for football clubs.

Revenue streams, expense tracking, financial health monitoring, budgets,
and Financial Fair Play compliance.  All monetary values are in millions
of euros unless otherwise noted.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from fm.db.models import (
    Club, League, Player, NewsItem, Transfer, LeagueStanding,
    Fixture, PlayerStats,
)
from fm.config import TV_MONEY_TIER1, TV_MONEY_TIER2


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Ticket pricing tiers (€ per person, converted to millions below)
_TICKET_GENERAL = 35.0
_TICKET_PREMIUM = 85.0
_TICKET_VIP = 250.0

# Proportion of stadium capacity per section
_SECTION_GENERAL_PCT = 0.75
_SECTION_PREMIUM_PCT = 0.20
_SECTION_VIP_PCT = 0.05

# Hospitality & extras per attendee (€)
_HOSPITALITY_PER_HEAD = 4.50
_FOOD_BEVERAGE_PER_HEAD = 6.00
_PARKING_PER_HEAD = 1.20

# Merchandise constants
_MERCH_BASE = 0.5          # M€ base for an average club
_MERCH_REP_MULT = 0.06     # extra per reputation point

# Sponsorship tiers by reputation band
_SPONSOR_TIERS = [
    (90, 25.0),   # elite: shirt deal ~25 M/year
    (75, 12.0),
    (60, 6.0),
    (45, 3.0),
    (30, 1.5),
    (0,  0.5),
]

# Prize money by league position (top-flight, in M€)
_PRIZE_MONEY_T1 = {
    1: 30.0, 2: 24.0, 3: 20.0, 4: 17.0, 5: 14.0,
    6: 12.0, 7: 10.0, 8: 8.5, 9: 7.0, 10: 6.0,
    11: 5.0, 12: 4.5, 13: 4.0, 14: 3.5, 15: 3.0,
    16: 2.5, 17: 2.0, 18: 1.5, 19: 1.0, 20: 0.8,
}

# Prize money for second-tier leagues (scaled down)
_PRIZE_MONEY_T2_SCALE = 0.20

# Facility maintenance per level (M€/season)
_FACILITY_COST_PER_LEVEL = 0.6

# Stadium maintenance as fraction of capacity
_STADIUM_MAINT_PER_SEAT = 0.0000005  # 0.5 €/seat/season → in M€

# FFP thresholds
_FFP_WAGE_REVENUE_LIMIT = 0.70       # 70% wage-to-revenue ratio
_FFP_MAX_LOSS_3YR = 30.0             # max 30M cumulative loss over 3 seasons

# Agent fee as percentage of transfer fee
_AGENT_FEE_PCT = 0.10

# Monthly overhead per reputation (staff salaries, scouting, medical etc.)
_OVERHEAD_BASE = 0.15                # M€/month base
_OVERHEAD_REP_MULT = 0.008           # extra per rep point per month


# ---------------------------------------------------------------------------
# Revenue Manager
# ---------------------------------------------------------------------------

class RevenueManager:
    """Calculates all forms of club income."""

    def __init__(self, session: Session):
        self.session = session

    # -- Matchday income -----------------------------------------------------

    def calculate_matchday_income(
        self,
        club_id: int,
        attendance: int | None = None,
        is_cup: bool = False,
    ) -> dict:
        """Return a breakdown of matchday revenue.

        Keys: gate_receipts, hospitality, food_beverage, parking, total
        """
        club = self.session.get(Club, club_id)
        if not club:
            return {"gate_receipts": 0, "hospitality": 0,
                    "food_beverage": 0, "parking": 0, "total": 0}

        capacity = club.stadium_capacity or 30000

        if attendance is None:
            # Estimate attendance from reputation
            fill_rate = min(0.95, 0.55 + (club.reputation or 50) / 200.0)
            if is_cup:
                fill_rate *= random.uniform(0.75, 0.95)
            attendance = int(capacity * fill_rate)

        attendance = min(attendance, capacity)

        # Gate receipts by section
        gen_seats = int(attendance * _SECTION_GENERAL_PCT)
        prem_seats = int(attendance * _SECTION_PREMIUM_PCT)
        vip_seats = attendance - gen_seats - prem_seats

        gate = (
            gen_seats * _TICKET_GENERAL
            + prem_seats * _TICKET_PREMIUM
            + vip_seats * _TICKET_VIP
        ) / 1_000_000  # to M€

        # Cup matches may have higher ticket prices
        if is_cup:
            gate *= 1.25

        hospitality = attendance * _HOSPITALITY_PER_HEAD / 1_000_000
        food_bev = attendance * _FOOD_BEVERAGE_PER_HEAD / 1_000_000
        parking = attendance * _PARKING_PER_HEAD / 1_000_000

        total = gate + hospitality + food_bev + parking

        return {
            "gate_receipts": round(gate, 4),
            "hospitality": round(hospitality, 4),
            "food_beverage": round(food_bev, 4),
            "parking": round(parking, 4),
            "total": round(total, 4),
            "attendance": attendance,
        }

    # -- TV money ------------------------------------------------------------

    def calculate_tv_money(
        self,
        club_id: int,
        league_id: int,
        season: int,
    ) -> float:
        """TV revenue based on league tier, equal share + merit-based portion."""
        league = self.session.get(League, league_id)
        if not league:
            return 0.0

        base_pool = TV_MONEY_TIER1 if league.tier == 1 else TV_MONEY_TIER2

        clubs = self.session.query(Club).filter_by(league_id=league_id).all()
        n_clubs = len(clubs) or 1

        # 50% equal share, 50% merit-based (by league position)
        equal_share = (base_pool * 0.5) / n_clubs

        # Merit share — try to find standing
        standing = self.session.query(LeagueStanding).filter_by(
            league_id=league_id, club_id=club_id, season=season,
        ).first()

        merit_share = 0.0
        if standing:
            # Rank clubs by points
            all_standings = (
                self.session.query(LeagueStanding)
                .filter_by(league_id=league_id, season=season)
                .order_by(
                    LeagueStanding.points.desc(),
                    LeagueStanding.goal_difference.desc(),
                )
                .all()
            )
            position = 1
            for i, st in enumerate(all_standings):
                if st.club_id == club_id:
                    position = i + 1
                    break

            # Higher position gets more of the merit pool
            merit_pool = base_pool * 0.5
            # Weight: top position gets double what bottom gets
            total_weight = sum(n_clubs - i for i in range(n_clubs))
            club_weight = max(n_clubs - position + 1, 1)
            merit_share = merit_pool * (club_weight / max(total_weight, 1))
        else:
            merit_share = (base_pool * 0.5) / n_clubs

        return round(equal_share + merit_share, 3)

    # -- Sponsorship ---------------------------------------------------------

    def calculate_sponsorship(self, club_id: int) -> dict:
        """Annual sponsorship income based on reputation.

        Returns: {shirt_sponsor, stadium_naming, training_kit, other, total}
        """
        club = self.session.get(Club, club_id)
        if not club:
            return {"shirt_sponsor": 0, "stadium_naming": 0,
                    "training_kit": 0, "other": 0, "total": 0}

        rep = club.reputation or 50

        # Find base tier
        base = 0.5
        for threshold, amount in _SPONSOR_TIERS:
            if rep >= threshold:
                base = amount
                break

        # Some random variation
        variation = random.uniform(0.85, 1.15)

        shirt = base * variation
        stadium_naming = shirt * 0.35
        training_kit = shirt * 0.15
        other = shirt * 0.20

        total = shirt + stadium_naming + training_kit + other

        return {
            "shirt_sponsor": round(shirt, 3),
            "stadium_naming": round(stadium_naming, 3),
            "training_kit": round(training_kit, 3),
            "other": round(other, 3),
            "total": round(total, 3),
        }

    # -- Prize money ---------------------------------------------------------

    def calculate_prize_money(
        self,
        club_id: int,
        league_id: int,
        season: int,
    ) -> float:
        """League position prize money."""
        league = self.session.get(League, league_id)
        if not league:
            return 0.0

        all_standings = (
            self.session.query(LeagueStanding)
            .filter_by(league_id=league_id, season=season)
            .order_by(
                LeagueStanding.points.desc(),
                LeagueStanding.goal_difference.desc(),
            )
            .all()
        )

        position = 0
        for i, st in enumerate(all_standings):
            if st.club_id == club_id:
                position = i + 1
                break

        if position == 0:
            return 0.0

        if league.tier == 1:
            return _PRIZE_MONEY_T1.get(position, 0.5)
        else:
            base = _PRIZE_MONEY_T1.get(position, 0.5)
            return round(base * _PRIZE_MONEY_T2_SCALE, 3)

    # -- Merchandise ---------------------------------------------------------

    def calculate_merchandise(self, club_id: int) -> float:
        """Annual merchandise revenue based on fanbase (reputation) and stars."""
        club = self.session.get(Club, club_id)
        if not club:
            return 0.0

        rep = club.reputation or 50
        base = _MERCH_BASE + rep * _MERCH_REP_MULT

        # Star player bonus — top player's overall adds extra pull
        top_player = (
            self.session.query(Player)
            .filter_by(club_id=club_id)
            .order_by(Player.overall.desc())
            .first()
        )
        star_bonus = 0.0
        if top_player and (top_player.overall or 0) >= 80:
            star_bonus = ((top_player.overall - 80) / 19.0) * 3.0  # up to ~3M

        return round(base + star_bonus, 3)


# ---------------------------------------------------------------------------
# Expense Manager
# ---------------------------------------------------------------------------

class ExpenseManager:
    """Tracks all forms of club expenditure."""

    def __init__(self, session: Session):
        self.session = session

    def calculate_wage_bill(self, club_id: int) -> dict:
        """Detailed wage breakdown.

        Returns: {player_wages_weekly, staff_weekly, total_weekly, annual}
        All wage values in thousands (K) of euros.
        """
        players = self.session.query(Player).filter_by(club_id=club_id).all()
        player_wages = sum(p.wage or 0 for p in players)

        # Staff wages estimated as 15% of player wages
        staff_wages = player_wages * 0.15

        total_weekly = player_wages + staff_wages
        annual = total_weekly * 52

        return {
            "player_wages_weekly": round(player_wages, 2),
            "staff_weekly": round(staff_wages, 2),
            "total_weekly": round(total_weekly, 2),
            "annual": round(annual, 2),
            "player_count": len(players),
        }

    def calculate_transfer_amortization(self, club_id: int, season: int) -> float:
        """Calculate annual amortized cost of transfer fees.

        Fees are spread evenly over the contract length.
        Returns M-euro annual amortization.
        """
        # Get transfers into this club in last 5 seasons
        transfers = (
            self.session.query(Transfer)
            .filter(
                Transfer.to_club_id == club_id,
                Transfer.fee > 0,
                Transfer.season >= season - 5,
            )
            .all()
        )

        total_annual = 0.0
        for t in transfers:
            # Get player contract length at time of transfer
            player = self.session.get(Player, t.player_id)
            if player:
                contract_years = max(
                    (player.contract_expiry or season + 3) - t.season, 1
                )
                annual_charge = t.fee / contract_years
                # Only count if still within amortization period
                years_elapsed = season - t.season
                if years_elapsed < contract_years:
                    total_annual += annual_charge

        return round(total_annual, 3)

    def calculate_facility_costs(self, club_id: int) -> float:
        """Annual facility maintenance costs (M-euro)."""
        club = self.session.get(Club, club_id)
        if not club:
            return 0.0

        facilities = club.facilities_level or 5
        capacity = club.stadium_capacity or 30000

        training_ground = facilities * _FACILITY_COST_PER_LEVEL
        stadium_maint = capacity * _STADIUM_MAINT_PER_SEAT * 1_000_000 / 1_000_000

        return round(training_ground + stadium_maint, 3)

    def calculate_agent_fees(self, club_id: int, season: int) -> float:
        """Accumulated agent fees from transfers this season."""
        transfers = (
            self.session.query(Transfer)
            .filter_by(to_club_id=club_id, season=season)
            .filter(Transfer.fee > 0)
            .all()
        )
        return round(
            sum(t.fee * _AGENT_FEE_PCT for t in transfers), 3
        )

    def calculate_monthly_overhead(self, club_id: int) -> float:
        """Monthly operational overhead (scouting, medical, admin, travel)."""
        club = self.session.get(Club, club_id)
        if not club:
            return 0.0

        rep = club.reputation or 50
        return round(_OVERHEAD_BASE + rep * _OVERHEAD_REP_MULT, 3)

    def calculate_bonus_payouts(self, club_id: int, season: int) -> float:
        """Estimate performance bonuses triggered this season."""
        standing = (
            self.session.query(LeagueStanding)
            .filter_by(club_id=club_id, season=season)
            .first()
        )
        if not standing:
            return 0.0

        # Win bonus estimate: ~5K per win, appearance bonuses etc.
        wins = standing.won or 0
        bonus_per_win = 0.005  # M€
        win_bonuses = wins * bonus_per_win

        # Goal bonuses for top scorers
        top_scorers = (
            self.session.query(PlayerStats)
            .filter_by(season=season)
            .join(Player, PlayerStats.player_id == Player.id)
            .filter(Player.club_id == club_id)
            .all()
        )
        goal_bonuses = sum(
            (ps.goals or 0) * 0.001 for ps in top_scorers  # 1K per goal
        )

        return round(win_bonuses + goal_bonuses, 3)


# ---------------------------------------------------------------------------
# Financial Health Monitor
# ---------------------------------------------------------------------------

class FinancialHealthMonitor:
    """Monitors and reports on club financial health."""

    def __init__(self, session: Session):
        self.session = session
        self.revenue_mgr = RevenueManager(session)
        self.expense_mgr = ExpenseManager(session)

    def get_financial_report(self, club_id: int, season: int) -> dict:
        """Complete profit & loss report for a season.

        Returns dict with revenue_breakdown, expense_breakdown, net_result,
        transfer_balance, wage_to_revenue_ratio, cash_in_bank.
        """
        club = self.session.get(Club, club_id)
        if not club:
            return {}

        league_id = club.league_id

        # Revenue
        tv = self.revenue_mgr.calculate_tv_money(
            club_id, league_id, season
        ) if league_id else 0.0

        sponsor = self.revenue_mgr.calculate_sponsorship(club_id)
        merch = self.revenue_mgr.calculate_merchandise(club_id)
        prize = self.revenue_mgr.calculate_prize_money(
            club_id, league_id, season
        ) if league_id else 0.0

        # Estimate total matchday revenue for the season (~19 home games)
        single_match = self.revenue_mgr.calculate_matchday_income(club_id)
        home_games = 19  # approximate
        matchday_total = single_match["total"] * home_games

        total_revenue = tv + sponsor["total"] + merch + prize + matchday_total

        # Expenses
        wages = self.expense_mgr.calculate_wage_bill(club_id)
        wages_annual_m = wages["annual"] / 1000.0  # K to M

        facilities = self.expense_mgr.calculate_facility_costs(club_id)
        amortization = self.expense_mgr.calculate_transfer_amortization(
            club_id, season
        )
        agent_fees = self.expense_mgr.calculate_agent_fees(club_id, season)
        overhead = self.expense_mgr.calculate_monthly_overhead(club_id) * 12
        bonuses = self.expense_mgr.calculate_bonus_payouts(club_id, season)

        total_expenses = (
            wages_annual_m + facilities + amortization
            + agent_fees + overhead + bonuses
        )

        # Transfer balance
        bought = (
            self.session.query(Transfer)
            .filter_by(to_club_id=club_id, season=season)
            .all()
        )
        sold = (
            self.session.query(Transfer)
            .filter_by(from_club_id=club_id, season=season)
            .all()
        )
        spent = sum(t.fee or 0 for t in bought)
        received = sum(t.fee or 0 for t in sold)
        transfer_balance = received - spent

        net_result = total_revenue - total_expenses + transfer_balance
        wtr = wages_annual_m / max(total_revenue, 0.01)

        return {
            "revenue": {
                "tv_money": round(tv, 2),
                "sponsorship": round(sponsor["total"], 2),
                "merchandise": round(merch, 2),
                "prize_money": round(prize, 2),
                "matchday": round(matchday_total, 2),
                "total": round(total_revenue, 2),
            },
            "expenses": {
                "wages": round(wages_annual_m, 2),
                "facilities": round(facilities, 2),
                "amortization": round(amortization, 2),
                "agent_fees": round(agent_fees, 2),
                "overhead": round(overhead, 2),
                "bonuses": round(bonuses, 2),
                "total": round(total_expenses, 2),
            },
            "transfer_balance": round(transfer_balance, 2),
            "net_result": round(net_result, 2),
            "wage_to_revenue_ratio": round(wtr, 3),
            "cash_in_bank": round(club.budget or 0, 2),
        }

    def check_ffp_compliance(self, club_id: int, season: int) -> dict:
        """Financial Fair Play compliance check.

        Returns: {compliant, wage_ratio, wage_ratio_ok, loss_3yr,
                  loss_3yr_ok, warnings}
        """
        warnings = []

        report = self.get_financial_report(club_id, season)
        if not report:
            return {"compliant": True, "warnings": []}

        wtr = report.get("wage_to_revenue_ratio", 0)
        wage_ok = wtr <= _FFP_WAGE_REVENUE_LIMIT
        if not wage_ok:
            warnings.append(
                f"Wage-to-revenue ratio {wtr:.1%} exceeds "
                f"{_FFP_WAGE_REVENUE_LIMIT:.0%} limit"
            )

        # Estimate 3-year cumulative loss (using current year as proxy)
        net = report.get("net_result", 0)
        loss_3yr = min(net * 3, 0)  # rough estimate
        loss_ok = abs(loss_3yr) <= _FFP_MAX_LOSS_3YR
        if not loss_ok:
            warnings.append(
                f"Projected 3-year loss of {abs(loss_3yr):.1f}M exceeds "
                f"{_FFP_MAX_LOSS_3YR:.0f}M FFP limit"
            )

        return {
            "compliant": wage_ok and loss_ok,
            "wage_ratio": round(wtr, 3),
            "wage_ratio_ok": wage_ok,
            "loss_3yr": round(loss_3yr, 2),
            "loss_3yr_ok": loss_ok,
            "warnings": warnings,
        }

    def project_finances(self, club_id: int, months: int = 6) -> dict:
        """Project finances forward N months.

        Returns: {projected_balance, monthly_burn, months_until_negative}
        """
        club = self.session.get(Club, club_id)
        if not club:
            return {}

        current_balance = club.budget or 0

        # Monthly income estimate
        rev_mgr = self.revenue_mgr
        single_match = rev_mgr.calculate_matchday_income(club_id)
        monthly_matchday = single_match["total"] * 2  # ~2 home games/month

        sponsor = rev_mgr.calculate_sponsorship(club_id)
        monthly_sponsor = sponsor["total"] / 12

        monthly_income = monthly_matchday + monthly_sponsor

        # Monthly expenses
        exp_mgr = self.expense_mgr
        wages = exp_mgr.calculate_wage_bill(club_id)
        monthly_wages = wages["total_weekly"] * 4.33 / 1000.0  # K to M

        monthly_overhead = exp_mgr.calculate_monthly_overhead(club_id)
        monthly_facilities = exp_mgr.calculate_facility_costs(club_id) / 12

        monthly_expenses = monthly_wages + monthly_overhead + monthly_facilities
        monthly_burn = monthly_income - monthly_expenses

        # Project forward
        projected = current_balance + monthly_burn * months

        # Months until negative
        if monthly_burn >= 0:
            months_neg = -1  # never
        elif current_balance <= 0:
            months_neg = 0
        else:
            months_neg = int(current_balance / abs(monthly_burn))

        return {
            "current_balance": round(current_balance, 2),
            "monthly_income": round(monthly_income, 3),
            "monthly_expenses": round(monthly_expenses, 3),
            "monthly_net": round(monthly_burn, 3),
            "projected_balance": round(projected, 2),
            "months_until_negative": months_neg,
        }

    def check_bankruptcy_risk(self, club_id: int) -> float:
        """Return 0.0-1.0 bankruptcy/administration risk score."""
        club = self.session.get(Club, club_id)
        if not club:
            return 0.0

        risk = 0.0
        balance = club.budget or 0

        # Negative balance is bad
        if balance < 0:
            risk += min(abs(balance) / 50.0, 0.4)  # up to 0.4

        # Wage bill vs budget
        wages = self.expense_mgr.calculate_wage_bill(club_id)
        annual_wages_m = wages["annual"] / 1000.0
        if annual_wages_m > 0 and balance < annual_wages_m * 0.5:
            risk += 0.15

        # Projection
        proj = self.project_finances(club_id, months=6)
        if proj.get("months_until_negative", -1) == 0:
            risk += 0.3
        elif 0 < proj.get("months_until_negative", -1) <= 3:
            risk += 0.15

        return min(risk, 1.0)


# ---------------------------------------------------------------------------
# Main FinanceManager (orchestrator)
# ---------------------------------------------------------------------------

class FinanceManager:
    """Orchestrates all financial operations for the game.

    Maintains backward compatibility with the original interface while
    providing access to the comprehensive sub-managers.
    """

    def __init__(self, session: Session):
        self.session = session
        self.revenue = RevenueManager(session)
        self.expenses = ExpenseManager(session)
        self.health = FinancialHealthMonitor(session)

    # -- Backward-compatible interface ---------------------------------------

    def process_matchday_income(
        self,
        club_id: int,
        attendance: int | None = None,
    ):
        """Add gate receipts and matchday revenue after a home match."""
        breakdown = self.revenue.calculate_matchday_income(
            club_id, attendance
        )
        club = self.session.get(Club, club_id)
        if club:
            club.budget = (club.budget or 0) + breakdown["total"]

    def process_season_tv_money(self, league_id: int, season: int):
        """Distribute TV money to all clubs in a league."""
        league = self.session.get(League, league_id)
        if not league:
            return

        clubs = self.session.query(Club).filter_by(league_id=league_id).all()
        for club in clubs:
            tv = self.revenue.calculate_tv_money(
                club.id, league_id, season
            )
            club.budget = (club.budget or 0) + tv

    def calculate_wage_bill(self, club_id: int) -> float:
        """Calculate total weekly player wages for a club (K-euro).

        Also updates Club.total_wages for display.
        """
        detail = self.expenses.calculate_wage_bill(club_id)
        total = detail["player_wages_weekly"]

        club = self.session.get(Club, club_id)
        if club:
            club.total_wages = total
        return total

    def process_weekly_wages(self):
        """Deduct weekly wages from all club budgets."""
        clubs = self.session.query(Club).all()
        for club in clubs:
            detail = self.expenses.calculate_wage_bill(club.id)
            # total_weekly includes staff; convert K to M
            weekly_cost = detail["total_weekly"] / 1000.0
            club.budget = (club.budget or 0) - weekly_cost
            club.total_wages = detail["player_wages_weekly"]

    def process_end_of_season_finances(self, season: int):
        """Comprehensive end-of-season financial processing."""
        leagues = self.session.query(League).all()

        # TV money distribution
        for league in leagues:
            self.process_season_tv_money(league.id, season)

        clubs = self.session.query(Club).all()
        for club in clubs:
            # Sponsorship income
            sponsor = self.revenue.calculate_sponsorship(club.id)
            club.budget = (club.budget or 0) + sponsor["total"]

            # Prize money
            if club.league_id:
                prize = self.revenue.calculate_prize_money(
                    club.id, club.league_id, season
                )
                club.budget = (club.budget or 0) + prize

            # Merchandise
            merch = self.revenue.calculate_merchandise(club.id)
            club.budget = (club.budget or 0) + merch

            # Facility maintenance cost
            fac_cost = self.expenses.calculate_facility_costs(club.id)
            club.budget = (club.budget or 0) - fac_cost

            # Overhead for remaining off-season months (~2 months)
            overhead = self.expenses.calculate_monthly_overhead(club.id) * 2
            club.budget = (club.budget or 0) - overhead

            # Agent fees
            agent = self.expenses.calculate_agent_fees(club.id, season)
            club.budget = (club.budget or 0) - agent

            # Set next season wage budget (55% of remaining budget, min 0)
            club.wage_budget = max(0, (club.budget or 0) * 0.55)

            # Check financial trouble
            if (club.budget or 0) < -10:
                risk = self.health.check_bankruptcy_risk(club.id)
                severity = "critical" if risk > 0.6 else "significant"
                self.session.add(NewsItem(
                    season=season,
                    headline=f"{club.name} in financial trouble!",
                    body=(
                        f"{club.name} are in {severity} debt "
                        f"({_fmt_currency(club.budget)}). "
                        f"The board demands cost-cutting measures."
                    ),
                    category="finance",
                ))
            elif (club.budget or 0) < -5:
                self.session.add(NewsItem(
                    season=season,
                    headline=f"{club.name} finances under pressure",
                    body=(
                        f"{club.name} ended the season with a balance of "
                        f"{_fmt_currency(club.budget)}. "
                        f"Careful spending will be needed."
                    ),
                    category="finance",
                ))

        self.session.commit()

    # -- New methods ---------------------------------------------------------

    def process_monthly_finances(self, season: int, month: int):
        """Process monthly financial operations (overhead, sponsorship drip).

        Call this at each calendar month boundary during the season.
        """
        clubs = self.session.query(Club).all()
        for club in clubs:
            # Monthly overhead
            overhead = self.expenses.calculate_monthly_overhead(club.id)
            club.budget = (club.budget or 0) - overhead

            # Sponsorship drip (1/12 of annual deal)
            sponsor = self.revenue.calculate_sponsorship(club.id)
            monthly_sponsor = sponsor["total"] / 12.0
            club.budget = (club.budget or 0) + monthly_sponsor

        self.session.flush()

    def get_budget_remaining(self, club_id: int) -> dict:
        """Return remaining transfer and wage budget.

        Returns: {transfer_budget, wage_budget_remaining, total_wages_weekly,
                  wage_budget_total}
        """
        club = self.session.get(Club, club_id)
        if not club:
            return {
                "transfer_budget": 0, "wage_budget_remaining": 0,
                "total_wages_weekly": 0, "wage_budget_total": 0,
            }

        detail = self.expenses.calculate_wage_bill(club_id)
        wages_weekly = detail["player_wages_weekly"]
        wage_budget = club.wage_budget or 0
        remaining_wage = max(0, wage_budget - wages_weekly)

        return {
            "transfer_budget": round(club.budget or 0, 2),
            "wage_budget_remaining": round(remaining_wage, 2),
            "total_wages_weekly": round(wages_weekly, 2),
            "wage_budget_total": round(wage_budget, 2),
        }

    def can_afford_wage(self, club_id: int, extra_wage: float) -> bool:
        """Check if a club can afford an additional weekly wage (K-euro)."""
        budget = self.get_budget_remaining(club_id)
        return budget["wage_budget_remaining"] >= extra_wage

    def get_wage_structure(self, club_id: int) -> dict:
        """Detailed wage structure analysis.

        Returns: {highest_earner, lowest_earner, median_wage,
                  average_wage, total_weekly, by_position, top_earners}
        """
        players = (
            self.session.query(Player)
            .filter_by(club_id=club_id)
            .order_by(Player.wage.desc())
            .all()
        )

        if not players:
            return {
                "highest_earner": None, "lowest_earner": None,
                "median_wage": 0, "average_wage": 0, "total_weekly": 0,
                "by_position": {}, "top_earners": [],
            }

        wages = [p.wage or 0 for p in players]
        wages_sorted = sorted(wages)

        # By position
        by_pos: dict[str, list[float]] = {}
        for p in players:
            pos = p.position or "?"
            by_pos.setdefault(pos, []).append(p.wage or 0)

        pos_averages = {
            pos: round(sum(w) / len(w), 1)
            for pos, w in by_pos.items()
        }

        # Top 5 earners
        top_earners = [
            {
                "name": p.short_name or p.name,
                "position": p.position,
                "wage": p.wage or 0,
                "overall": p.overall or 0,
            }
            for p in players[:5]
        ]

        median_idx = len(wages_sorted) // 2
        median = wages_sorted[median_idx]

        return {
            "highest_earner": {
                "name": players[0].short_name or players[0].name,
                "wage": players[0].wage or 0,
            },
            "lowest_earner": {
                "name": players[-1].short_name or players[-1].name,
                "wage": players[-1].wage or 0,
            },
            "median_wage": round(median, 1),
            "average_wage": round(sum(wages) / len(wages), 1),
            "total_weekly": round(sum(wages), 1),
            "by_position": pos_averages,
            "top_earners": top_earners,
        }

    def process_bonus_payment(
        self,
        club_id: int,
        player_id: int,
        bonus_type: str,
        amount: float,
    ):
        """Process a bonus payment (amount in M-euro)."""
        club = self.session.get(Club, club_id)
        if club:
            club.budget = (club.budget or 0) - amount

    def process_transfer_payment(
        self,
        buyer_id: int,
        seller_id: int,
        amount: float,
        installments: int = 1,
    ):
        """Process transfer fee between clubs.

        If installments > 1, only the first installment is taken immediately.
        The remaining amount is treated as deferred (simplified: we deduct
        the full amount from buyer now and credit full to seller, since we
        don't yet model deferred payments across seasons).
        """
        buyer = self.session.get(Club, buyer_id)
        seller = self.session.get(Club, seller_id)

        if not buyer or not seller:
            return

        if installments > 1:
            # Immediate portion
            immediate = amount / installments
            deferred = amount - immediate

            buyer.budget = (buyer.budget or 0) - immediate
            seller.budget = (seller.budget or 0) + immediate

            # For simplicity, deduct remaining from buyer in one go
            # but credit seller the full deferred (they can spend against it)
            buyer.budget = (buyer.budget or 0) - deferred
            seller.budget = (seller.budget or 0) + deferred
        else:
            buyer.budget = (buyer.budget or 0) - amount
            seller.budget = (seller.budget or 0) + amount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_currency(amount: float | None) -> str:
    """Format a M-euro amount for display."""
    if amount is None:
        return "N/A"
    if abs(amount) >= 1.0:
        return f"\u20ac{amount:.1f}M"
    return f"\u20ac{amount * 1000:.0f}K"
