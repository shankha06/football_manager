"""Transfer market simulation.

Handles player valuation, market search, transfer/loan listings,
transfer window management, AI transfer activity, and rumour generation.
Negotiation logic lives in fm.world.contracts.
"""
from __future__ import annotations

import math
import random
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from fm.db.models import Player, Club, Transfer, NewsItem, League, PlayerStats
from fm.config import STARTING_SEASON


# Top-5 league countries (players from these leagues valued higher)
TOP_LEAGUE_COUNTRIES = {"England", "Spain", "Germany", "Italy", "France"}

# Position scarcity multipliers: quality players in scarce positions cost more
_POSITION_SCARCITY: dict[str, float] = {
    "GK": 0.80,   # keepers generally cheaper but quality ones hold value
    "CB": 1.10,
    "LB": 1.00,
    "RB": 1.00,
    "LWB": 0.95,
    "RWB": 0.95,
    "CDM": 1.05,
    "CM": 1.00,
    "CAM": 1.05,
    "LM": 0.95,
    "RM": 0.95,
    "LW": 1.10,
    "RW": 1.10,
    "CF": 1.15,
    "ST": 1.20,   # strikers command highest premiums
}

# Transfer window schedule (matchday ranges)
# Summer window: matchdays 0-6 (pre-season + early season)
# January window: matchdays 19-22 (mid-season)
_SUMMER_WINDOW = (0, 6)
_JANUARY_WINDOW = (19, 22)


class TransferMarket:
    """Handles all transfer market activity: search, valuation, listings."""

    def __init__(self, session: Session):
        self.session = session
        # In-memory tracking of transfer/loan listed players
        self._transfer_listed: dict[int, float] = {}   # player_id -> asking price
        self._loan_listed: set[int] = set()             # player_id set

    # == Search ============================================================

    def search_players(
        self,
        position: str | None = None,
        min_overall: int = 0,
        max_value: float = 999.0,
        exclude_club_id: int | None = None,
        max_age: int | None = None,
        min_age: int | None = None,
        nationality: str | None = None,
        free_agents_only: bool = False,
        max_results: int = 50,
    ) -> list[Player]:
        """Search for available players on the market."""
        q = self.session.query(Player)

        if free_agents_only:
            q = q.filter(Player.club_id.is_(None))
        if position:
            q = q.filter(Player.position == position)
        if min_overall:
            q = q.filter(Player.overall >= min_overall)
        if max_value < 999.0:
            q = q.filter(Player.market_value <= max_value)
        if exclude_club_id:
            q = q.filter(Player.club_id != exclude_club_id)
        if max_age:
            q = q.filter(Player.age <= max_age)
        if min_age:
            q = q.filter(Player.age >= min_age)
        if nationality:
            q = q.filter(Player.nationality == nationality)

        q = q.order_by(Player.overall.desc())
        return q.limit(max_results).all()

    def get_free_agents(
        self,
        position: str | None = None,
        min_overall: int = 0,
        max_results: int = 50,
    ) -> list[Player]:
        """Get players without a club."""
        q = self.session.query(Player).filter(Player.club_id.is_(None))
        if position:
            q = q.filter(Player.position == position)
        if min_overall:
            q = q.filter(Player.overall >= min_overall)
        return q.order_by(Player.overall.desc()).limit(max_results).all()

    def search_by_name(self, name: str, max_results: int = 20) -> list[Player]:
        """Search players by name (partial match)."""
        pattern = f"%{name}%"
        return (
            self.session.query(Player)
            .filter(
                or_(
                    Player.name.ilike(pattern),
                    Player.short_name.ilike(pattern),
                )
            )
            .order_by(Player.overall.desc())
            .limit(max_results)
            .all()
        )

    # == Enhanced Valuation ================================================

    def calculate_market_value(self, player: Player) -> float:
        """Calculate a player's market value using a comprehensive algorithm.

        Uses non-linear ability scaling, age curves, contract leverage,
        form/potential premiums, league inflation, and position scarcity.
        Returns value in millions EUR.
        """
        overall = player.overall or 50
        age = player.age or 25

        # -- Base value: shifted power curve (only 60+ OVR have real value) --
        # 50 ovr ~ 0.1M, 70 ovr ~ 17M, 80 ovr ~ 50M, 85 ovr ~ 77M, 91 ovr ~ 120M
        normalised = max(0, (overall - 45)) / 54.0  # maps 45-99 to 0-1
        base = (normalised ** 3.2) * 200.0

        # -- Age multiplier: peaks at 25-27, drops sharply after 30 --
        age_mult = _age_value_multiplier(age)

        # -- Contract years: each year adds ~15% --
        years_left = max(
            (player.contract_expiry or STARTING_SEASON) - STARTING_SEASON, 0
        )
        contract_mult = 0.40 + min(years_left, 5) * 0.15  # 0.40 - 1.15

        # -- Form bonus: good form adds up to 15% --
        form = player.form or 65.0
        form_mult = 1.0
        if form >= 80:
            form_mult = 1.15
        elif form >= 70:
            form_mult = 1.08
        elif form < 40:
            form_mult = 0.90

        # -- Potential premium: young players with high potential --
        pot_premium = 0.0
        potential = player.potential or overall
        if age <= 23 and potential > overall:
            gap = potential - overall
            # Non-linear: bigger gaps are worth disproportionately more
            pot_premium = (gap / 99.0) ** 1.5 * 80.0
            # Extra bonus for very young players
            if age <= 20:
                pot_premium *= 1.4
            elif age <= 18:
                pot_premium *= 1.8

        # -- League inflation: top-5 league players worth 30% more --
        league_mult = 1.0
        if player.club_id:
            club = self.session.get(Club, player.club_id)
            if club and club.league_id:
                league = self.session.get(League, club.league_id)
                if league:
                    if league.country in TOP_LEAGUE_COUNTRIES:
                        league_mult = 1.30
                    elif league.tier == 1:
                        league_mult = 1.10

        # -- Position scarcity --
        pos = player.position or "CM"
        pos_mult = _POSITION_SCARCITY.get(pos, 1.0)
        # Quality GKs and CBs have a higher floor
        if pos == "GK" and overall >= 82:
            pos_mult = 1.05  # top keepers are valuable
        elif pos == "CB" and overall >= 80:
            pos_mult = 1.15

        # -- Injury history: injury-prone players lose value --
        injury_proneness = player.injury_proneness or 30
        injury_mult = 1.0
        if injury_proneness >= 70:
            injury_mult = 0.80
        elif injury_proneness >= 55:
            injury_mult = 0.90

        # -- Homegrown / domestic premium --
        # (Simplified: players at clubs in their home country get a small bump)
        homegrown_mult = 1.0
        if player.club_id and player.nationality:
            club = self.session.get(Club, player.club_id)
            if club and club.league_id:
                league = self.session.get(League, club.league_id)
                if league and _is_homegrown(player.nationality, league.country):
                    homegrown_mult = 1.08

        value = (
            base
            * age_mult
            * contract_mult
            * form_mult
            * league_mult
            * pos_mult
            * injury_mult
            * homegrown_mult
            + pot_premium
        )

        return round(max(0.05, value), 2)

    # == Transfer & Loan Listings ==========================================

    def get_transfer_listed_players(self) -> list[Player]:
        """Get all players currently listed for transfer."""
        if not self._transfer_listed:
            return []
        player_ids = list(self._transfer_listed.keys())
        return (
            self.session.query(Player)
            .filter(Player.id.in_(player_ids))
            .order_by(Player.overall.desc())
            .all()
        )

    def list_player_for_transfer(
        self,
        club_id: int,
        player_id: int,
        asking_price: float | None = None,
    ) -> bool:
        """List a player for transfer sale."""
        player = self.session.get(Player, player_id)
        if not player or player.club_id != club_id:
            return False

        if asking_price is None:
            asking_price = self.calculate_market_value(player)

        self._transfer_listed[player_id] = asking_price

        club = self.session.get(Club, club_id)
        self.session.add(NewsItem(
            season=STARTING_SEASON,
            headline=f"{player.short_name or player.name} transfer listed by "
                     f"{club.name if club else 'unknown'}",
            body=f"{player.name} has been made available for transfer "
                 f"at an asking price of \u20ac{asking_price:.1f}M.",
            category="transfer",
        ))

        return True

    def delist_player(self, club_id: int, player_id: int) -> bool:
        """Remove a player from the transfer list."""
        player = self.session.get(Player, player_id)
        if not player or player.club_id != club_id:
            return False
        self._transfer_listed.pop(player_id, None)
        return True

    def get_asking_price(self, player_id: int) -> float | None:
        """Get the asking price for a transfer-listed player."""
        return self._transfer_listed.get(player_id)

    def is_transfer_listed(self, player_id: int) -> bool:
        """Check if a player is transfer listed."""
        return player_id in self._transfer_listed

    def get_loan_listed_players(self) -> list[Player]:
        """Get all players currently listed for loan."""
        if not self._loan_listed:
            return []
        return (
            self.session.query(Player)
            .filter(Player.id.in_(list(self._loan_listed)))
            .order_by(Player.overall.desc())
            .all()
        )

    def list_player_for_loan(self, club_id: int, player_id: int) -> bool:
        """List a player as available for loan."""
        player = self.session.get(Player, player_id)
        if not player or player.club_id != club_id:
            return False

        self._loan_listed.add(player_id)

        club = self.session.get(Club, club_id)
        self.session.add(NewsItem(
            season=STARTING_SEASON,
            headline=f"{player.short_name or player.name} available for loan",
            body=f"{club.name if club else 'Unknown'} are willing to let "
                 f"{player.name} leave on loan.",
            category="transfer",
        ))

        return True

    def delist_loan_player(self, club_id: int, player_id: int) -> bool:
        """Remove a player from the loan list."""
        player = self.session.get(Player, player_id)
        if not player or player.club_id != club_id:
            return False
        self._loan_listed.discard(player_id)
        return True

    # == Transfer Window Management ========================================

    def is_transfer_window_open(self, season) -> bool:
        """Check if a transfer window is currently open.

        Args:
            season: Season ORM object with current_matchday attribute.
        """
        md = season.current_matchday if hasattr(season, 'current_matchday') else 0
        phase = getattr(season, 'phase', '')

        # Pre-season is always open
        if phase == "pre_season":
            return True

        # Summer window
        if _SUMMER_WINDOW[0] <= md <= _SUMMER_WINDOW[1]:
            return True

        # January window
        if _JANUARY_WINDOW[0] <= md <= _JANUARY_WINDOW[1]:
            return True

        return False

    def is_deadline_day(self, season) -> bool:
        """Check if it's the last day of a transfer window."""
        md = season.current_matchday if hasattr(season, 'current_matchday') else 0
        return md == _SUMMER_WINDOW[1] or md == _JANUARY_WINDOW[1]

    def get_deadline_day_deals(self, season) -> list[Transfer]:
        """Get all transfers completed on deadline day."""
        md = season.current_matchday if hasattr(season, 'current_matchday') else 0
        year = season.year if hasattr(season, 'year') else STARTING_SEASON
        return (
            self.session.query(Transfer)
            .filter_by(season=year)
            .all()
        )

    # == Legacy Bid Interface (backward compat with existing code) =========

    def make_bid(
        self,
        buyer_club_id: int,
        player_id: int,
        bid_amount: float,
        season: int,
    ) -> bool:
        """Submit a bid for a player. Returns True if accepted.

        This is the simplified legacy interface. For full negotiation with
        clauses and counters, use fm.world.contracts.TransferNegotiator.
        """
        player = self.session.get(Player, player_id)
        if not player or not player.club_id:
            return False

        buyer = self.session.get(Club, buyer_club_id)
        seller = self.session.get(Club, player.club_id)
        if not buyer or not seller:
            return False

        # AI negotiation logic
        fair_value = self.calculate_market_value(player)

        # Selling club's willingness (reputation-scaled)
        multiplier = 1.0 + (seller.reputation or 50) / 200.0
        ask_price = fair_value * multiplier

        # Squad importance check: key players cost more
        squad = self.session.query(Player).filter_by(
            club_id=seller.id
        ).order_by(Player.overall.desc()).limit(3).all()
        is_key = player.id in {p.id for p in squad}
        if is_key:
            ask_price *= 1.50

        # Contract leverage
        years_left = max(
            (player.contract_expiry or STARTING_SEASON) - STARTING_SEASON, 0
        )
        if years_left <= 1:
            ask_price *= 0.70

        # If bid meets or exceeds asking price, accept
        if bid_amount >= ask_price * 0.90:
            return self._complete_transfer(
                player, buyer, seller, bid_amount, season
            )

        return False

    def sign_free_agent(
        self,
        club_id: int,
        player_id: int,
        wage: float,
        season: int,
    ) -> bool:
        """Sign a free agent."""
        player = self.session.get(Player, player_id)
        club = self.session.get(Club, club_id)
        if not player or not club or player.club_id:
            return False

        player.club_id = club_id
        player.wage = wage
        player.contract_expiry = season + random.randint(2, 4)

        transfer = Transfer(
            player_id=player_id,
            from_club_id=None,
            to_club_id=club_id,
            fee=0.0,
            wage=wage,
            season=season,
        )
        self.session.add(transfer)

        self.session.add(NewsItem(
            season=season,
            headline=f"{player.name} signs for {club.name} on a free transfer",
            body=f"{player.name} has joined {club.name} as a free agent "
                 f"on a wage of \u20ac{wage:.0f}K/week.",
            category="transfer",
        ))

        return True

    def _complete_transfer(
        self,
        player: Player,
        buyer: Club,
        seller: Club,
        fee: float,
        season: int,
    ) -> bool:
        """Execute a completed transfer."""
        if (buyer.budget or 0) < fee:
            return False

        old_club_name = seller.name

        # Financial adjustments
        buyer.budget = (buyer.budget or 0) - fee
        seller.budget = (seller.budget or 0) + fee

        # Wage
        new_wage = player.wage * random.uniform(1.0, 1.3)  # slight raise

        # Record
        transfer = Transfer(
            player_id=player.id,
            from_club_id=seller.id,
            to_club_id=buyer.id,
            fee=fee,
            wage=new_wage,
            season=season,
        )
        self.session.add(transfer)

        # Update player
        player.club_id = buyer.id
        player.wage = new_wage
        player.contract_expiry = season + random.randint(3, 5)
        player.market_value = self.calculate_market_value(player)

        # News
        self.session.add(NewsItem(
            season=season,
            headline=f"{player.name} joins {buyer.name} from {old_club_name}",
            body=f"{buyer.name} have signed {player.name} from {old_club_name} "
                 f"for \u20ac{fee:.1f}M.",
            category="transfer",
        ))

        # Remove from listings if present
        self._transfer_listed.pop(player.id, None)
        self._loan_listed.discard(player.id)

        return True

    # == AI Transfer Activity ==============================================

    def process_ai_transfers(self, season, matchday: int) -> list[dict]:
        """AI clubs make transfer moves during open windows.

        Called each matchday. Returns list of completed deal summaries.
        """
        if not self.is_transfer_window_open(season):
            return []

        deals = []
        year = season.year if hasattr(season, 'year') else STARTING_SEASON
        is_deadline = self.is_deadline_day(season)

        from fm.db.models import Manager
        ai_managers = (
            self.session.query(Manager)
            .filter_by(is_human=False)
            .all()
        )

        for mgr in ai_managers:
            if not mgr.club_id:
                continue

            club = self.session.get(Club, mgr.club_id)
            if not club or (club.budget or 0) < 1.0:
                continue

            # Evaluate squad needs
            needs = self._evaluate_squad_needs(club.id)
            if not needs:
                continue

            # Probability of acting: higher on deadline day
            act_chance = 0.08 if not is_deadline else 0.35
            if random.random() > act_chance:
                continue

            # Try to fill one need
            position = random.choice(needs)
            max_spend = (club.budget or 0) * random.uniform(0.20, 0.50)

            # Search for targets
            targets = self.search_players(
                position=position,
                max_value=max_spend,
                exclude_club_id=club.id,
                max_results=10,
            )

            if not targets:
                # Try free agents
                free = self.get_free_agents(position=position, min_overall=55)
                if free:
                    target = random.choice(free[:5])
                    wage = self._suggest_wage_for_player(target, club)
                    if self.sign_free_agent(club.id, target.id, wage, year):
                        deals.append({
                            "type": "free_agent",
                            "player": target.name,
                            "club": club.name,
                            "wage": wage,
                        })
                continue

            # Pick a target and bid
            target = random.choice(targets[:5])
            value = self.calculate_market_value(target)
            bid_amount = value * random.uniform(0.90, 1.25)

            # Deadline day panic: overbid
            if is_deadline:
                bid_amount *= random.uniform(1.10, 1.40)

            success = self.make_bid(
                buyer_club_id=club.id,
                player_id=target.id,
                bid_amount=bid_amount,
                season=year,
            )
            if success:
                deals.append({
                    "type": "transfer",
                    "player": target.name,
                    "from_club": target.club.name if target.club else "Unknown",
                    "to_club": club.name,
                    "fee": bid_amount,
                })

        if deals:
            self.session.flush()

        return deals

    def generate_transfer_rumors(self, season) -> list[NewsItem]:
        """Generate transfer rumour news items for atmosphere.

        Creates plausible-sounding rumours about potential moves.
        """
        year = season.year if hasattr(season, 'year') else STARTING_SEASON
        rumors: list[NewsItem] = []

        # Get some high-profile players at clubs
        top_players = (
            self.session.query(Player)
            .filter(Player.club_id.isnot(None), Player.overall >= 75)
            .order_by(Player.overall.desc())
            .limit(50)
            .all()
        )

        if not top_players:
            return rumors

        # Pick a few for rumours
        num_rumors = random.randint(1, 3)
        candidates = random.sample(top_players, min(num_rumors, len(top_players)))

        big_clubs = (
            self.session.query(Club)
            .filter(Club.reputation >= 75)
            .all()
        )

        rumor_templates = [
            ("{player} attracting interest from {club}",
             "Sources say {club} are monitoring {player}'s situation at "
             "{current_club}. No formal bid has been made yet."),
            ("{club} eyeing move for {player}",
             "{club} are reportedly preparing a bid for {current_club}'s "
             "{player}, valued at around \u20ac{value:.0f}M."),
            ("{player} could leave {current_club} this window",
             "Reports suggest {player} is open to a move away from "
             "{current_club}. Several clubs are said to be interested."),
            ("Agent of {player} in talks with {club}",
             "The agent of {current_club}'s {player} has reportedly held "
             "preliminary discussions with {club}."),
        ]

        for player in candidates:
            if not player.club_id or not big_clubs:
                continue

            current_club = self.session.get(Club, player.club_id)
            if not current_club:
                continue

            # Pick a different club for the rumour
            other_clubs = [c for c in big_clubs if c.id != player.club_id]
            if not other_clubs:
                continue

            linked_club = random.choice(other_clubs)
            template = random.choice(rumor_templates)
            value = self.calculate_market_value(player)

            headline = template[0].format(
                player=player.short_name or player.name,
                club=linked_club.name,
                current_club=current_club.name,
            )
            body = template[1].format(
                player=player.name,
                club=linked_club.name,
                current_club=current_club.name,
                value=value,
            )

            news = NewsItem(
                season=year,
                headline=headline,
                body=body,
                category="transfer",
            )
            self.session.add(news)
            rumors.append(news)

        if rumors:
            self.session.flush()

        return rumors

    # == Squad & Wage Analysis =============================================

    def calculate_squad_value(self, club_id: int) -> float:
        """Calculate total squad market value for a club (millions EUR)."""
        players = (
            self.session.query(Player)
            .filter_by(club_id=club_id)
            .all()
        )
        return sum(self.calculate_market_value(p) for p in players)

    def get_wage_structure(self, club_id: int) -> dict:
        """Get wage breakdown by position group.

        Returns dict with keys: 'total', 'gk', 'def', 'mid', 'att',
        'top_earner', 'average', 'count'.
        """
        players = (
            self.session.query(Player)
            .filter_by(club_id=club_id)
            .all()
        )
        if not players:
            return {
                "total": 0.0, "gk": 0.0, "def": 0.0,
                "mid": 0.0, "att": 0.0,
                "top_earner": None, "average": 0.0, "count": 0,
            }

        gk_wages = 0.0
        def_wages = 0.0
        mid_wages = 0.0
        att_wages = 0.0
        top_earner = None
        top_wage = 0.0

        for p in players:
            w = p.wage or 0.0
            pos = p.position or "CM"
            if pos == "GK":
                gk_wages += w
            elif pos in ("CB", "LB", "RB", "LWB", "RWB"):
                def_wages += w
            elif pos in ("CDM", "CM", "CAM", "LM", "RM"):
                mid_wages += w
            else:
                att_wages += w

            if w > top_wage:
                top_wage = w
                top_earner = p

        total = gk_wages + def_wages + mid_wages + att_wages

        return {
            "total": round(total, 1),
            "gk": round(gk_wages, 1),
            "def": round(def_wages, 1),
            "mid": round(mid_wages, 1),
            "att": round(att_wages, 1),
            "top_earner": {
                "name": top_earner.short_name or top_earner.name,
                "wage": top_wage,
                "position": top_earner.position,
            } if top_earner else None,
            "average": round(total / len(players), 1),
            "count": len(players),
        }

    def suggest_wage_for_player(self, player: Player, club: Club) -> float:
        """Suggest an appropriate wage offer for a player at a given club.

        Public wrapper around internal method.
        """
        return self._suggest_wage_for_player(player, club)

    def get_expiring_contracts(
        self, club_id: int, within_years: int = 1
    ) -> list[Player]:
        """Get players whose contracts expire soon."""
        threshold = STARTING_SEASON + within_years
        return (
            self.session.query(Player)
            .filter(
                Player.club_id == club_id,
                Player.contract_expiry <= threshold,
            )
            .order_by(Player.overall.desc())
            .all()
        )

    def get_recent_transfers(
        self, season: int | None = None, limit: int = 20
    ) -> list[Transfer]:
        """Get recent transfers, optionally filtered by season."""
        q = self.session.query(Transfer)
        if season is not None:
            q = q.filter_by(season=season)
        return q.order_by(Transfer.id.desc()).limit(limit).all()

    def get_club_transfers(self, club_id: int, season: int) -> list[Transfer]:
        """Get all transfers involving a specific club in a season."""
        return (
            self.session.query(Transfer)
            .filter(
                Transfer.season == season,
                or_(
                    Transfer.from_club_id == club_id,
                    Transfer.to_club_id == club_id,
                ),
            )
            .order_by(Transfer.id.desc())
            .all()
        )

    # == Internal helpers ==================================================

    def _suggest_wage_for_player(
        self, player: Player, club: Club
    ) -> float:
        """Calculate a reasonable wage offer (thousands EUR/week).

        Based on player ability, club wage structure, and market rates.
        """
        overall = player.overall or 50
        age = player.age or 25

        # Base wage from ability
        if overall >= 90:
            base = random.uniform(250, 450)
        elif overall >= 85:
            base = random.uniform(150, 280)
        elif overall >= 80:
            base = random.uniform(80, 160)
        elif overall >= 75:
            base = random.uniform(40, 90)
        elif overall >= 70:
            base = random.uniform(20, 50)
        elif overall >= 65:
            base = random.uniform(10, 25)
        elif overall >= 60:
            base = random.uniform(5, 12)
        else:
            base = random.uniform(1, 5)

        # Adjust for club's wage budget
        club_wage_budget = club.wage_budget or 0.0
        if club_wage_budget > 0:
            # Don't offer more than ~15% of club's budget for one player
            cap = club_wage_budget * 0.15
            base = min(base, cap)

        # Age adjustment
        if 26 <= age <= 29:
            base *= 1.10
        elif age >= 32:
            base *= 0.85
        elif age <= 21:
            base *= 0.70

        return round(max(0.5, base), 1)

    def _evaluate_squad_needs(self, club_id: int) -> list[str]:
        """Return positions where the squad needs reinforcement."""
        players = (
            self.session.query(Player)
            .filter_by(club_id=club_id)
            .all()
        )

        position_counts: dict[str, int] = {}
        for p in players:
            pos = p.position
            position_counts[pos] = position_counts.get(pos, 0) + 1

        needs = []
        requirements = {
            "GK": 2, "CB": 3, "LB": 1, "RB": 1,
            "CM": 2, "CDM": 1, "ST": 2, "LW": 1, "RW": 1,
        }
        for pos, min_count in requirements.items():
            current = position_counts.get(pos, 0)
            if current < min_count:
                needs.extend([pos] * (min_count - current))

        return needs


# == Module-level helpers ==================================================

def _age_value_multiplier(age: int) -> float:
    """Return a multiplier for player value based on age.

    Peaks at 25-27, drops sharply after 30, and is low for very young players
    (limited proven track record).
    """
    if age <= 17:
        return 0.30
    elif age <= 19:
        return 0.55
    elif age <= 21:
        return 0.80
    elif age <= 23:
        return 1.05
    elif age <= 25:
        return 1.20
    elif age <= 27:
        return 1.25  # peak
    elif age <= 29:
        return 1.10
    elif age == 30:
        return 0.85
    elif age == 31:
        return 0.70
    elif age == 32:
        return 0.55
    elif age == 33:
        return 0.40
    elif age == 34:
        return 0.28
    elif age == 35:
        return 0.18
    else:
        return 0.10


def _is_homegrown(nationality: str, league_country: str) -> bool:
    """Check if a player's nationality matches the league's country.

    Uses a simple mapping for common cases.
    """
    _COUNTRY_MAP = {
        "England": {"England", "Wales", "Scotland", "Northern Ireland"},
        "Spain": {"Spain"},
        "Germany": {"Germany"},
        "Italy": {"Italy"},
        "France": {"France"},
        "Portugal": {"Portugal"},
        "Netherlands": {"Netherlands", "Holland"},
    }
    valid = _COUNTRY_MAP.get(league_country, {league_country})
    return nationality in valid
