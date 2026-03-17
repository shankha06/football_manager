"""Contract negotiation and transfer deal engine.

Handles contract offers, renewals, wage demands, player willingness,
transfer bids with clauses, loan deals, and AI bid evaluation.
Separated from transfer_market.py which handles market search/valuation.
"""
from __future__ import annotations

import enum
import math
import random
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from fm.db.models import Club, Player, Transfer, NewsItem, League, PlayerStats
from fm.config import STARTING_SEASON


# -- Enums & Constants -----------------------------------------------------

class SquadRole(str, enum.Enum):
    KEY_PLAYER = "key_player"
    FIRST_TEAM = "first_team"
    ROTATION = "rotation"
    BACKUP = "backup"
    YOUTH = "youth"


class NegotiationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTER = "counter"
    EXPIRED = "expired"
    PLAYER_REJECTED = "player_rejected"
    COMPLETED = "completed"


class BidStatus(str, enum.Enum):
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COUNTER = "counter"
    PLAYER_NEGOTIATION = "player_negotiation"
    COMPLETED = "completed"
    COLLAPSED = "collapsed"


# Wage brackets by overall rating (weekly, in thousands EUR)
_WAGE_BRACKETS: list[tuple[int, float, float]] = [
    # (min_overall, min_wage, max_wage) -- thousands per week
    (90, 250.0, 500.0),
    (85, 150.0, 300.0),
    (80, 80.0, 180.0),
    (75, 40.0, 100.0),
    (70, 20.0, 55.0),
    (65, 10.0, 30.0),
    (60, 5.0, 15.0),
    (55, 2.0, 8.0),
    (0, 0.5, 3.0),
]

# Squad-role wage multipliers (what the player expects relative to base)
_ROLE_WAGE_MULT: dict[str, float] = {
    SquadRole.KEY_PLAYER: 1.25,
    SquadRole.FIRST_TEAM: 1.0,
    SquadRole.ROTATION: 0.85,
    SquadRole.BACKUP: 0.70,
    SquadRole.YOUTH: 0.50,
}

# Top-5 league countries (players from these leagues demand more)
TOP_LEAGUE_COUNTRIES = {"England", "Spain", "Germany", "Italy", "France"}


# -- Data Classes ----------------------------------------------------------

@dataclass
class ContractOffer:
    """A contract proposal from a club to a player."""
    wage_per_week: float            # thousands EUR
    contract_years: int             # 1-5
    signing_bonus: float = 0.0      # millions EUR
    release_clause: float | None = None  # millions EUR, None = no clause
    appearance_bonus: float = 0.0   # thousands EUR per appearance
    goal_bonus: float = 0.0         # thousands EUR per goal
    assist_bonus: float = 0.0       # thousands EUR per assist
    clean_sheet_bonus: float = 0.0  # thousands EUR per clean sheet (GK/DEF)
    squad_role: str = SquadRole.FIRST_TEAM
    agent_fee_pct: float = 10.0     # percentage of transfer fee or annual wage


@dataclass
class NegotiationResult:
    """Outcome of a negotiation round."""
    status: NegotiationStatus
    message: str
    counter_offer: ContractOffer | None = None
    willingness: float = 0.0        # 0-1, how willing the player is
    rounds_remaining: int = 0


@dataclass
class BidDetails:
    """Transfer bid details submitted by a buying club."""
    amount: float                   # millions EUR
    add_ons: float = 0.0            # millions EUR in performance add-ons
    sell_on_pct: float = 0.0        # percentage of future sale profit
    buy_back_clause: float | None = None  # millions EUR
    exchange_player_id: int | None = None
    is_loan: bool = False
    loan_fee: float = 0.0           # millions EUR loan fee
    loan_wage_pct: float = 100.0    # percentage of wages the borrowing club pays
    loan_option_to_buy: float | None = None  # optional purchase price


@dataclass
class BidResult:
    """Outcome of a transfer bid."""
    status: BidStatus
    message: str
    bid_id: int = 0
    counter_amount: float | None = None
    counter_details: BidDetails | None = None


@dataclass
class ActiveNegotiation:
    """Tracks an ongoing negotiation between a club and player."""
    negotiation_id: int
    club_id: int
    player_id: int
    current_offer: ContractOffer
    rounds_completed: int = 0
    max_rounds: int = 3
    status: NegotiationStatus = NegotiationStatus.PENDING


@dataclass
class ActiveBid:
    """Tracks an ongoing transfer bid."""
    bid_id: int
    bidding_club_id: int
    selling_club_id: int
    player_id: int
    details: BidDetails
    status: BidStatus = BidStatus.SUBMITTED
    counter_count: int = 0
    max_counters: int = 3


# -- Contract Negotiator ---------------------------------------------------

class ContractNegotiator:
    """Handles contract proposals, renewals, and wage negotiations."""

    def __init__(self, session: Session):
        self.session = session
        self._next_neg_id = 1
        self._negotiations: dict[int, ActiveNegotiation] = {}

    # -- Public API --------------------------------------------------------

    def propose_contract(
        self,
        club_id: int,
        player_id: int,
        offer: ContractOffer,
    ) -> NegotiationResult:
        """Propose a contract to a player (new signing or after bid accepted).

        The player must either be a free agent or have an accepted bid in place.
        """
        player = self.session.get(Player, player_id)
        club = self.session.get(Club, club_id)
        if not player or not club:
            return NegotiationResult(
                status=NegotiationStatus.REJECTED,
                message="Invalid player or club.",
            )

        willingness = self.player_willingness_to_sign(player, club, offer)
        agent_demands = self.calculate_agent_demands(player, offer)

        # Check if offer meets minimum demands
        wage_demand = self.calculate_wage_demand(player)
        wage_ratio = offer.wage_per_week / max(wage_demand, 0.1)

        # Create negotiation tracker
        neg_id = self._next_neg_id
        self._next_neg_id += 1

        neg = ActiveNegotiation(
            negotiation_id=neg_id,
            club_id=club_id,
            player_id=player_id,
            current_offer=offer,
        )

        if willingness >= 0.75 and wage_ratio >= 0.90:
            neg.status = NegotiationStatus.ACCEPTED
            self._negotiations[neg_id] = neg
            return NegotiationResult(
                status=NegotiationStatus.ACCEPTED,
                message=f"{player.short_name or player.name} accepts the contract.",
                willingness=willingness,
            )

        if willingness < 0.25:
            neg.status = NegotiationStatus.REJECTED
            self._negotiations[neg_id] = neg
            return NegotiationResult(
                status=NegotiationStatus.REJECTED,
                message=f"{player.short_name or player.name} is not interested "
                        f"in joining {club.name}.",
                willingness=willingness,
            )

        # Player counters
        counter = self._generate_counter_offer(player, club, offer, wage_demand)
        neg.status = NegotiationStatus.COUNTER
        neg.current_offer = offer
        self._negotiations[neg_id] = neg

        return NegotiationResult(
            status=NegotiationStatus.COUNTER,
            message=f"{player.short_name or player.name}'s agent demands "
                    f"better terms.",
            counter_offer=counter,
            willingness=willingness,
            rounds_remaining=neg.max_rounds - neg.rounds_completed,
        )

    def propose_renewal(
        self,
        club_id: int,
        player_id: int,
        offer: ContractOffer,
    ) -> NegotiationResult:
        """Propose a contract renewal to a player already at the club."""
        player = self.session.get(Player, player_id)
        club = self.session.get(Club, club_id)
        if not player or not club:
            return NegotiationResult(
                status=NegotiationStatus.REJECTED,
                message="Invalid player or club.",
            )
        if player.club_id != club_id:
            return NegotiationResult(
                status=NegotiationStatus.REJECTED,
                message=f"{player.short_name or player.name} is not at this club.",
            )

        # Renewals are easier -- player already knows the club
        willingness = self.player_willingness_to_sign(player, club, offer)
        # Loyalty bonus for renewals
        willingness = min(1.0, willingness + 0.15)

        wage_demand = self.calculate_wage_demand(player)
        # Players expect a raise on renewal
        renewal_demand = max(wage_demand, (player.wage or 0) * 1.10)
        wage_ratio = offer.wage_per_week / max(renewal_demand, 0.1)

        if willingness >= 0.65 and wage_ratio >= 0.85:
            return NegotiationResult(
                status=NegotiationStatus.ACCEPTED,
                message=f"{player.short_name or player.name} agrees to a new deal.",
                willingness=willingness,
            )

        if willingness < 0.20 or wage_ratio < 0.50:
            return NegotiationResult(
                status=NegotiationStatus.REJECTED,
                message=f"{player.short_name or player.name} refuses to renew.",
                willingness=willingness,
            )

        counter = self._generate_counter_offer(
            player, club, offer, renewal_demand
        )
        return NegotiationResult(
            status=NegotiationStatus.COUNTER,
            message=f"{player.short_name or player.name}'s agent requests "
                    f"improved terms.",
            counter_offer=counter,
            willingness=willingness,
            rounds_remaining=3,
        )

    def negotiate_round(self, negotiation_id: int) -> NegotiationResult:
        """Continue a pending negotiation. Each round players may soften demands."""
        neg = self._negotiations.get(negotiation_id)
        if not neg or neg.status not in (
            NegotiationStatus.PENDING, NegotiationStatus.COUNTER
        ):
            return NegotiationResult(
                status=NegotiationStatus.EXPIRED,
                message="Negotiation not found or already concluded.",
            )

        player = self.session.get(Player, neg.player_id)
        club = self.session.get(Club, neg.club_id)
        if not player or not club:
            return NegotiationResult(
                status=NegotiationStatus.EXPIRED,
                message="Invalid negotiation state.",
            )

        neg.rounds_completed += 1
        offer = neg.current_offer
        willingness = self.player_willingness_to_sign(player, club, offer)

        # Each round the player softens slightly (eager to conclude)
        softening = neg.rounds_completed * 0.08
        willingness = min(1.0, willingness + softening)

        wage_demand = self.calculate_wage_demand(player)
        # Demands drop slightly each round
        adjusted_demand = wage_demand * (1.0 - neg.rounds_completed * 0.05)
        wage_ratio = offer.wage_per_week / max(adjusted_demand, 0.1)

        if willingness >= 0.65 and wage_ratio >= 0.85:
            neg.status = NegotiationStatus.ACCEPTED
            return NegotiationResult(
                status=NegotiationStatus.ACCEPTED,
                message=f"{player.short_name or player.name} agrees to the deal "
                        f"after negotiations.",
                willingness=willingness,
            )

        if neg.rounds_completed >= neg.max_rounds:
            neg.status = NegotiationStatus.EXPIRED
            return NegotiationResult(
                status=NegotiationStatus.EXPIRED,
                message=f"Negotiations with {player.short_name or player.name} "
                        f"have broken down.",
                willingness=willingness,
            )

        # Generate new counter
        counter = self._generate_counter_offer(
            player, club, offer, adjusted_demand
        )
        neg.status = NegotiationStatus.COUNTER

        return NegotiationResult(
            status=NegotiationStatus.COUNTER,
            message=f"Round {neg.rounds_completed}: agent adjusts demands.",
            counter_offer=counter,
            willingness=willingness,
            rounds_remaining=neg.max_rounds - neg.rounds_completed,
        )

    def calculate_wage_demand(self, player: Player) -> float:
        """Calculate what weekly wage a player demands (thousands EUR).

        Based on overall rating, age, reputation context, and current wages.
        """
        overall = player.overall or 50
        age = player.age or 25
        current_wage = player.wage or 0.0

        # Find bracket
        base_min, base_max = 0.5, 3.0
        for min_ovr, w_min, w_max in _WAGE_BRACKETS:
            if overall >= min_ovr:
                base_min, base_max = w_min, w_max
                break

        # Interpolate within bracket
        base = base_min + (base_max - base_min) * random.uniform(0.3, 0.7)

        # Age adjustments: prime-age players demand more
        if 26 <= age <= 29:
            base *= 1.15  # peak earning years
        elif age >= 32:
            base *= 0.85  # willing to take less
        elif age <= 21:
            base *= 0.75  # young, happy for opportunity

        # Player won't accept less than current wage (unless desperate)
        floor = current_wage * 0.90
        demand = max(base, floor)

        # League prestige: players in top leagues expect more
        if player.club_id:
            club = self.session.get(Club, player.club_id)
            if club and club.league_id:
                league = self.session.get(League, club.league_id)
                if league and league.country in TOP_LEAGUE_COUNTRIES:
                    demand *= 1.15

        return round(demand, 1)

    def calculate_agent_demands(
        self, player: Player, offer: ContractOffer
    ) -> dict:
        """Calculate agent fee and other demands.

        Returns dict with agent_fee (millions), signing_bonus_demand, etc.
        """
        overall = player.overall or 50
        age = player.age or 25

        # Agent fee percentage: higher-profile players have greedier agents
        if overall >= 85:
            agent_pct = random.uniform(10.0, 15.0)
        elif overall >= 75:
            agent_pct = random.uniform(7.0, 12.0)
        elif overall >= 65:
            agent_pct = random.uniform(5.0, 8.0)
        else:
            agent_pct = random.uniform(3.0, 6.0)

        # Annual wage for fee calculation
        annual_wage = offer.wage_per_week * 52 / 1000.0  # millions
        agent_fee = annual_wage * (agent_pct / 100.0)

        # Signing bonus demand (free agents demand more)
        is_free = player.club_id is None
        if is_free:
            signing_bonus = annual_wage * random.uniform(0.3, 0.8)
        elif overall >= 80:
            signing_bonus = annual_wage * random.uniform(0.1, 0.3)
        else:
            signing_bonus = 0.0

        # Release clause demand (more common for high-profile players)
        wants_release_clause = random.random() < (overall / 200.0)
        release_clause = None
        if wants_release_clause:
            # Set at roughly 2-3x player value
            from fm.world.transfer_market import TransferMarket
            tm = TransferMarket(self.session)
            value = tm.calculate_market_value(player)
            release_clause = round(value * random.uniform(2.0, 3.5), 1)

        return {
            "agent_fee": round(agent_fee, 2),
            "agent_fee_pct": round(agent_pct, 1),
            "signing_bonus_demand": round(signing_bonus, 2),
            "wants_release_clause": wants_release_clause,
            "release_clause_demand": release_clause,
        }

    def player_willingness_to_sign(
        self,
        player: Player,
        club: Club,
        offer: ContractOffer,
    ) -> float:
        """Calculate how willing a player is to sign (0.0 to 1.0).

        Considers many factors: reputation, wages, role, ambition, loyalty, age.
        """
        score = 0.5  # neutral starting point

        # -- Club reputation vs current club --
        target_rep = club.reputation or 50
        current_rep = 30  # free agent baseline
        if player.club_id:
            current_club = self.session.get(Club, player.club_id)
            if current_club:
                current_rep = current_club.reputation or 50

        rep_diff = target_rep - current_rep
        # Moving to a bigger club is attractive
        score += _clamp(rep_diff / 100.0, -0.20, 0.25)

        # -- Wage comparison --
        current_wage = player.wage or 1.0
        wage_ratio = offer.wage_per_week / max(current_wage, 0.1)
        if wage_ratio >= 1.5:
            score += 0.15
        elif wage_ratio >= 1.1:
            score += 0.08
        elif wage_ratio < 0.85:
            score -= 0.15
        elif wage_ratio < 0.95:
            score -= 0.05

        # -- Squad role --
        role = offer.squad_role
        overall = player.overall or 50
        if role == SquadRole.KEY_PLAYER and overall >= 75:
            score += 0.10
        elif role == SquadRole.KEY_PLAYER and overall < 70:
            score += 0.15  # flattered by role above station
        elif role == SquadRole.BACKUP and overall >= 78:
            score -= 0.15  # too good for backup
        elif role == SquadRole.YOUTH and overall >= 70:
            score -= 0.20  # insulting
        elif role == SquadRole.ROTATION and overall >= 82:
            score -= 0.10

        # -- Ambition factor (derived from overall + composure) --
        # High-ability players with high composure are ambitious
        ambition = (overall + (player.composure or 50)) / 200.0
        if ambition > 0.7 and target_rep < current_rep:
            score -= 0.15  # ambitious player won't step down
        elif ambition > 0.7 and target_rep > current_rep + 15:
            score += 0.10  # drawn to bigger clubs

        # -- Loyalty factor (derived from consistency) --
        loyalty = (player.consistency or 65) / 100.0
        if loyalty > 0.75 and player.club_id is not None:
            score -= 0.10  # loyal, reluctant to leave

        # -- Age factor --
        age = player.age or 25
        if age >= 30:
            # Older players value playing time
            if role in (SquadRole.KEY_PLAYER, SquadRole.FIRST_TEAM):
                score += 0.10
            elif role == SquadRole.BACKUP:
                score -= 0.10
        if age >= 33:
            # Veterans more willing to move for guaranteed football
            score += 0.05

        if age <= 21:
            # Young players want development
            if target_rep > current_rep:
                score += 0.05  # step up is exciting
            # High facilities = better development
            if (club.facilities_level or 5) >= 7:
                score += 0.05

        # -- Contract length preference --
        years = offer.contract_years
        if age >= 31 and years >= 4:
            score += 0.08  # older player loves long-term security
        elif age <= 23 and years >= 5:
            score -= 0.05  # young player wary of being locked in
        elif years <= 1:
            score -= 0.10  # too short, no security

        # -- Performance bonuses sweeten the deal --
        bonus_total = (
            offer.appearance_bonus
            + offer.goal_bonus
            + offer.assist_bonus
            + offer.clean_sheet_bonus
        )
        if bonus_total > 0:
            score += min(bonus_total / 50.0, 0.08)

        # -- Signing bonus --
        if offer.signing_bonus > 0:
            score += min(offer.signing_bonus / 5.0, 0.10)

        # -- Morale / happiness at current club --
        morale = player.morale or 65.0
        if morale < 40:
            score += 0.15  # unhappy, wants out
        elif morale < 55:
            score += 0.05
        elif morale > 80:
            score -= 0.10  # happy where they are

        # -- Random human element --
        score += random.uniform(-0.08, 0.08)

        return _clamp(score, 0.0, 1.0)

    # -- Internal helpers --------------------------------------------------

    def _generate_counter_offer(
        self,
        player: Player,
        club: Club,
        original: ContractOffer,
        wage_demand: float,
    ) -> ContractOffer:
        """Generate a player's counter-offer based on their demands."""
        # Wage: split the difference, leaning toward player's demand
        counter_wage = (wage_demand * 0.65 + original.wage_per_week * 0.35)
        counter_wage = max(counter_wage, original.wage_per_week * 1.05)

        # Contract years: player may want longer or shorter
        age = player.age or 25
        if age >= 30:
            desired_years = min(original.contract_years + 1, 5)
        elif age <= 22:
            desired_years = max(original.contract_years - 1, 2)
        else:
            desired_years = original.contract_years

        # Signing bonus: agent always pushes for one
        counter_bonus = max(
            original.signing_bonus,
            counter_wage * 52 / 1000.0 * 0.15,  # 15% of annual in millions
        )

        # Appearance bonus
        counter_app = max(original.appearance_bonus, 2.0)

        return ContractOffer(
            wage_per_week=round(counter_wage, 1),
            contract_years=desired_years,
            signing_bonus=round(counter_bonus, 2),
            release_clause=original.release_clause,
            appearance_bonus=round(counter_app, 1),
            goal_bonus=max(original.goal_bonus, 1.0),
            assist_bonus=max(original.assist_bonus, 0.5),
            clean_sheet_bonus=original.clean_sheet_bonus,
            squad_role=original.squad_role,
            agent_fee_pct=min(original.agent_fee_pct + 2.0, 15.0),
        )

    def finalize_contract(
        self,
        club_id: int,
        player_id: int,
        offer: ContractOffer,
        season: int,
        transfer_fee: float = 0.0,
        from_club_id: int | None = None,
        is_loan: bool = False,
        loan_end_season: int | None = None,
    ) -> bool:
        """Apply an accepted contract: update player record, create Transfer."""
        player = self.session.get(Player, player_id)
        club = self.session.get(Club, club_id)
        if not player or not club:
            return False

        old_club_id = player.club_id
        old_club_name = "Free Agency"
        if old_club_id:
            old_club = self.session.get(Club, old_club_id)
            if old_club:
                old_club_name = old_club.name

        # Financial: deduct signing bonus + agent fee from budget
        agent_fee = (
            offer.wage_per_week * 52 / 1000.0 * (offer.agent_fee_pct / 100.0)
        )
        total_cost = offer.signing_bonus + agent_fee
        club.budget = (club.budget or 0) - total_cost

        # Update player
        player.club_id = club_id
        player.wage = offer.wage_per_week
        player.contract_expiry = season + offer.contract_years
        player.morale = min(100.0, (player.morale or 65.0) + 10.0)

        # Record transfer
        transfer = Transfer(
            player_id=player_id,
            from_club_id=from_club_id or old_club_id,
            to_club_id=club_id,
            fee=transfer_fee,
            wage=offer.wage_per_week,
            season=season,
            is_loan=is_loan,
            loan_end_season=loan_end_season,
        )
        self.session.add(transfer)

        # News
        if is_loan:
            headline = (
                f"{player.short_name or player.name} joins {club.name} on loan"
            )
            body = (
                f"{player.name} has joined {club.name} on loan from "
                f"{old_club_name} until {loan_end_season}."
            )
        elif transfer_fee > 0:
            headline = (
                f"{player.short_name or player.name} signs for {club.name} "
                f"for {_format_fee(transfer_fee)}"
            )
            body = (
                f"{player.name} has completed a move from {old_club_name} to "
                f"{club.name} for {_format_fee(transfer_fee)}. "
                f"He signs a {offer.contract_years}-year deal."
            )
        else:
            headline = (
                f"{player.short_name or player.name} signs for {club.name} "
                f"on a free"
            )
            body = (
                f"{player.name} has joined {club.name} as a free agent on a "
                f"{offer.contract_years}-year contract worth "
                f"{_format_wage(offer.wage_per_week)}/week."
            )

        self.session.add(NewsItem(
            season=season,
            headline=headline,
            body=body,
            category="transfer",
        ))

        self.session.flush()
        return True


# -- Transfer Negotiator ---------------------------------------------------

class TransferNegotiator:
    """Handles club-to-club transfer negotiations: bids, counters, deals."""

    def __init__(self, session: Session):
        self.session = session
        self._next_bid_id = 1
        self._bids: dict[int, ActiveBid] = {}

    # -- Public API --------------------------------------------------------

    def submit_bid(
        self,
        bidding_club_id: int,
        player_id: int,
        bid_details: BidDetails,
    ) -> BidResult:
        """Submit a transfer bid for a player."""
        player = self.session.get(Player, player_id)
        buyer = self.session.get(Club, bidding_club_id)
        if not player or not buyer:
            return BidResult(
                status=BidStatus.REJECTED, message="Invalid player or club."
            )
        if not player.club_id:
            return BidResult(
                status=BidStatus.REJECTED,
                message=f"{player.short_name or player.name} is a free agent. "
                        f"No bid needed.",
            )
        if player.club_id == bidding_club_id:
            return BidResult(
                status=BidStatus.REJECTED,
                message="Cannot bid on your own player.",
            )

        seller = self.session.get(Club, player.club_id)
        if not seller:
            return BidResult(
                status=BidStatus.REJECTED, message="Selling club not found."
            )

        # Check buyer can afford it
        total_upfront = bid_details.amount + (
            bid_details.loan_fee if bid_details.is_loan else 0.0
        )
        if (buyer.budget or 0) < total_upfront:
            return BidResult(
                status=BidStatus.REJECTED,
                message=f"{buyer.name} cannot afford this bid "
                        f"(budget: {_format_fee(buyer.budget or 0)}).",
            )

        # AI evaluation of the bid
        response = self.evaluate_bid(bid_details, player, seller)

        bid_id = self._next_bid_id
        self._next_bid_id += 1

        bid = ActiveBid(
            bid_id=bid_id,
            bidding_club_id=bidding_club_id,
            selling_club_id=seller.id,
            player_id=player_id,
            details=bid_details,
        )

        if response == "accept":
            bid.status = BidStatus.ACCEPTED
            self._bids[bid_id] = bid
            return BidResult(
                status=BidStatus.ACCEPTED,
                message=f"{seller.name} accept the bid of "
                        f"{_format_fee(bid_details.amount)} for "
                        f"{player.short_name or player.name}.",
                bid_id=bid_id,
            )

        if response == "reject":
            bid.status = BidStatus.REJECTED
            self._bids[bid_id] = bid
            return BidResult(
                status=BidStatus.REJECTED,
                message=f"{seller.name} reject the bid outright.",
                bid_id=bid_id,
            )

        # Counter offer
        counter_amount = self._generate_counter_bid(
            bid_details, player, seller
        )
        bid.status = BidStatus.COUNTER
        bid.counter_count += 1
        self._bids[bid_id] = bid

        counter_details = BidDetails(
            amount=counter_amount,
            sell_on_pct=min(bid_details.sell_on_pct, 15.0),
            is_loan=bid_details.is_loan,
            loan_fee=bid_details.loan_fee,
            loan_wage_pct=bid_details.loan_wage_pct,
        )

        return BidResult(
            status=BidStatus.COUNTER,
            message=f"{seller.name} want {_format_fee(counter_amount)} "
                    f"for {player.short_name or player.name}.",
            bid_id=bid_id,
            counter_amount=counter_amount,
            counter_details=counter_details,
        )

    def respond_to_bid(
        self,
        bid_id: int,
        response: str,
        revised_amount: float | None = None,
    ) -> BidResult:
        """Respond to a counter-offer: 'accept', 'reject', or 'counter'.

        For 'counter', provide revised_amount.
        """
        bid = self._bids.get(bid_id)
        if not bid:
            return BidResult(
                status=BidStatus.REJECTED, message="Bid not found."
            )

        player = self.session.get(Player, bid.player_id)
        seller = self.session.get(Club, bid.selling_club_id)
        if not player or not seller:
            return BidResult(
                status=BidStatus.COLLAPSED,
                message="Deal has collapsed.",
            )

        if response == "accept":
            bid.status = BidStatus.ACCEPTED
            return BidResult(
                status=BidStatus.ACCEPTED,
                message=f"Bid accepted. Proceed to personal terms with "
                        f"{player.short_name or player.name}.",
                bid_id=bid_id,
            )

        if response == "reject":
            bid.status = BidStatus.REJECTED
            return BidResult(
                status=BidStatus.REJECTED,
                message="You have withdrawn from negotiations.",
                bid_id=bid_id,
            )

        # Counter
        if bid.counter_count >= bid.max_counters:
            bid.status = BidStatus.REJECTED
            return BidResult(
                status=BidStatus.REJECTED,
                message=f"{seller.name} are tired of negotiating and reject "
                        f"the bid.",
                bid_id=bid_id,
            )

        if revised_amount is None:
            return BidResult(
                status=BidStatus.COUNTER,
                message="Provide a revised amount.",
                bid_id=bid_id,
            )

        bid.details.amount = revised_amount
        bid.counter_count += 1

        # Re-evaluate
        eval_result = self.evaluate_bid(bid.details, player, seller)
        if eval_result == "accept":
            bid.status = BidStatus.ACCEPTED
            return BidResult(
                status=BidStatus.ACCEPTED,
                message=f"{seller.name} accept the revised bid of "
                        f"{_format_fee(revised_amount)}.",
                bid_id=bid_id,
            )

        if eval_result == "reject":
            bid.status = BidStatus.REJECTED
            return BidResult(
                status=BidStatus.REJECTED,
                message=f"{seller.name} reject the revised bid.",
                bid_id=bid_id,
            )

        # Another counter
        counter_amount = self._generate_counter_bid(
            bid.details, player, seller
        )
        return BidResult(
            status=BidStatus.COUNTER,
            message=f"{seller.name} counter with {_format_fee(counter_amount)}.",
            bid_id=bid_id,
            counter_amount=counter_amount,
        )

    def calculate_asking_price(
        self, player: Player, selling_club: Club
    ) -> float:
        """Calculate what a selling club would ask for a player."""
        from fm.world.transfer_market import TransferMarket
        tm = TransferMarket(self.session)
        base_value = tm.calculate_market_value(player)

        club_rep = selling_club.reputation or 50
        # Rich/prestigious clubs hold out for more
        rep_mult = 1.0 + (club_rep / 200.0)

        # Contract leverage: more years = higher price
        years_left = max(
            (player.contract_expiry or STARTING_SEASON) - STARTING_SEASON, 0
        )
        if years_left >= 4:
            contract_mult = 1.25
        elif years_left >= 3:
            contract_mult = 1.10
        elif years_left >= 2:
            contract_mult = 1.00
        elif years_left == 1:
            contract_mult = 0.70  # desperate to sell
        else:
            contract_mult = 0.40  # about to leave for free

        # Squad importance: best players cost more
        squad = self.session.query(Player).filter_by(
            club_id=selling_club.id
        ).order_by(Player.overall.desc()).limit(5).all()
        top_ids = {p.id for p in squad}
        importance_mult = 1.50 if player.id in top_ids else 1.00

        # Player unhappy? Lowers price
        morale = player.morale or 65.0
        morale_mult = 1.0
        if morale < 35:
            morale_mult = 0.80
        elif morale < 50:
            morale_mult = 0.90

        price = (
            base_value * rep_mult * contract_mult
            * importance_mult * morale_mult
        )
        return round(max(0.1, price), 1)

    def evaluate_bid(
        self,
        bid: BidDetails,
        player: Player,
        selling_club: Club,
    ) -> str:
        """AI logic: evaluate a bid and return 'accept', 'reject', or 'counter'."""
        asking = self.calculate_asking_price(player, selling_club)
        total_value = bid.amount + bid.add_ons * 0.5  # add-ons worth ~50%

        ratio = total_value / max(asking, 0.1)

        # -- Squad importance --
        squad = self.session.query(Player).filter_by(
            club_id=selling_club.id
        ).order_by(Player.overall.desc()).limit(3).all()
        is_key = player.id in {p.id for p in squad}
        if is_key:
            # Key players need at least 150% of asking price
            ratio *= 0.67  # effectively raises the bar

        # -- Contract years --
        years_left = max(
            (player.contract_expiry or STARTING_SEASON) - STARTING_SEASON, 0
        )
        if years_left <= 1:
            ratio *= 1.30  # desperate, lower standards

        # -- Financial pressure --
        if (selling_club.budget or 0) < -5.0:
            ratio *= 1.20  # in debt, more willing

        # -- Player wants to leave --
        morale = player.morale or 65.0
        if morale < 35:
            ratio *= 1.15

        # -- Sell-on clause sweetener --
        if bid.sell_on_pct >= 15:
            ratio *= 0.97  # seller doesn't love giving up future profit

        # -- Loan deals: different evaluation --
        if bid.is_loan:
            # Loan evaluation: is the fee reasonable + option to buy
            loan_value = bid.loan_fee
            if bid.loan_option_to_buy:
                loan_value += bid.loan_option_to_buy * 0.3
            loan_ratio = loan_value / max(asking * 0.15, 0.1)
            if loan_ratio >= 0.8:
                return "accept"
            elif loan_ratio >= 0.5:
                return "counter"
            return "reject"

        # -- Decision thresholds --
        if ratio >= 0.95:
            return "accept"
        elif ratio >= 0.70:
            return "counter"
        else:
            return "reject"

    def add_clauses(self, bid_id: int, clauses: dict) -> None:
        """Add clauses to an existing bid.

        Supported keys: sell_on_pct, buy_back_clause, add_ons,
        exchange_player_id.
        """
        bid = self._bids.get(bid_id)
        if not bid:
            return

        if "sell_on_pct" in clauses:
            bid.details.sell_on_pct = float(clauses["sell_on_pct"])
        if "buy_back_clause" in clauses:
            bid.details.buy_back_clause = float(clauses["buy_back_clause"])
        if "add_ons" in clauses:
            bid.details.add_ons = float(clauses["add_ons"])
        if "exchange_player_id" in clauses:
            bid.details.exchange_player_id = int(clauses["exchange_player_id"])

    def complete_transfer(
        self, bid_id: int, contract_offer: ContractOffer, season: int
    ) -> bool:
        """Complete an accepted transfer bid: move player, adjust finances."""
        bid = self._bids.get(bid_id)
        if not bid or bid.status != BidStatus.ACCEPTED:
            return False

        player = self.session.get(Player, bid.player_id)
        buyer = self.session.get(Club, bid.bidding_club_id)
        seller = self.session.get(Club, bid.selling_club_id)
        if not player or not buyer or not seller:
            return False

        fee = bid.details.amount

        # Check budget
        if (buyer.budget or 0) < fee:
            bid.status = BidStatus.COLLAPSED
            return False

        # Financial adjustments
        buyer.budget = (buyer.budget or 0) - fee
        seller.budget = (seller.budget or 0) + fee

        # Finalize contract
        cn = ContractNegotiator(self.session)
        success = cn.finalize_contract(
            club_id=bid.bidding_club_id,
            player_id=bid.player_id,
            offer=contract_offer,
            season=season,
            transfer_fee=fee,
            from_club_id=bid.selling_club_id,
        )

        if success:
            bid.status = BidStatus.COMPLETED
            # Update market value
            from fm.world.transfer_market import TransferMarket
            tm = TransferMarket(self.session)
            player.market_value = tm.calculate_market_value(player)
            self.session.flush()

        return success

    def process_loan_deal(
        self,
        bid_id: int,
        season: int,
        loan_end_season: int | None = None,
    ) -> bool:
        """Process an accepted loan deal."""
        bid = self._bids.get(bid_id)
        if not bid or bid.status != BidStatus.ACCEPTED:
            return False
        if not bid.details.is_loan:
            return False

        player = self.session.get(Player, bid.player_id)
        buyer = self.session.get(Club, bid.bidding_club_id)
        seller = self.session.get(Club, bid.selling_club_id)
        if not player or not buyer or not seller:
            return False

        end = loan_end_season or (season + 1)

        # Loan fee
        if bid.details.loan_fee > 0:
            buyer.budget = (buyer.budget or 0) - bid.details.loan_fee
            seller.budget = (seller.budget or 0) + bid.details.loan_fee

        # Wage contribution
        original_wage = player.wage or 0
        loan_wage = original_wage * (bid.details.loan_wage_pct / 100.0)

        # Create a simple contract for the loan period
        loan_offer = ContractOffer(
            wage_per_week=loan_wage,
            contract_years=end - season,
            squad_role=SquadRole.FIRST_TEAM,
            agent_fee_pct=0.0,
        )

        cn = ContractNegotiator(self.session)
        success = cn.finalize_contract(
            club_id=bid.bidding_club_id,
            player_id=bid.player_id,
            offer=loan_offer,
            season=season,
            from_club_id=bid.selling_club_id,
            is_loan=True,
            loan_end_season=end,
        )

        if success:
            bid.status = BidStatus.COMPLETED
            self.session.flush()

        return success

    # -- Internal helpers --------------------------------------------------

    def _generate_counter_bid(
        self,
        original: BidDetails,
        player: Player,
        seller: Club,
    ) -> float:
        """Generate selling club's counter-offer amount."""
        asking = self.calculate_asking_price(player, seller)
        offered = original.amount

        # Counter somewhere between asking price and offered amount
        # Biased toward asking price
        counter = asking * 0.7 + offered * 0.3
        # At least higher than what was offered
        counter = max(counter, offered * 1.10)
        # But not absurdly high
        counter = min(counter, asking * 1.20)

        return round(counter, 1)

    def get_bid(self, bid_id: int) -> ActiveBid | None:
        """Retrieve a bid by ID."""
        return self._bids.get(bid_id)


# -- Module helpers --------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _format_fee(amount: float) -> str:
    """Format a fee in millions for display."""
    if amount >= 1.0:
        return f"\u20ac{amount:.1f}M"
    return f"\u20ac{amount * 1000:.0f}K"


def _format_wage(wage: float) -> str:
    """Format weekly wage (in thousands) for display."""
    if wage >= 1000:
        return f"\u20ac{wage / 1000:.1f}M"
    return f"\u20ac{wage:.0f}K"
