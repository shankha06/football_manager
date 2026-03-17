"""Narrative Engine and Saga Tracker.

Turns discrete events into multi-matchday stories.
"""
from __future__ import annotations
import random
import json
from fm.db.models import Player, Club, NewsItem, Saga, NewsCategory

class NarrativeEngine:
    def __init__(self, session):
        self.session = session

    def process_matchday_entities(self, season_year: int, matchday: int):
        """Scan for new narrative triggers and advance existing sagas."""
        self._advance_existing_sagas(season_year, matchday)
        self._trigger_new_sagas(season_year, matchday)

    def _advance_existing_sagas(self, season_year: int, matchday: int):
        active_sagas = self.session.query(Saga).filter_by(is_active=True).all()
        for saga in active_sagas:
            if saga.type == "transfer_unrest":
                self._handle_transfer_saga(saga, season_year, matchday)
            elif saga.type == "contract_standoff":
                self._handle_contract_saga(saga, season_year, matchday)

    def _trigger_new_sagas(self, season_year: int, matchday: int):
        """Identify potential stories (e.g. high-value player with low morale)."""
        # 1. Transfer Unrest Trigger
        unhappy_stars = (
            self.session.query(Player)
            .filter(Player.morale < 40)
            .filter(Player.overall >= 72)
            .filter(Player.club_id.isnot(None))
            .all()
        )
        
        for p in unhappy_stars:
            # Check if already in a saga
            existing = self.session.query(Saga).filter_by(target_id=p.id, type="transfer_unrest", is_active=True).first()
            if not existing and random.random() < 0.2:
                new_saga = Saga(
                    type="transfer_unrest",
                    target_id=p.id,
                    club_id=p.club_id,
                    stage=1,
                    data=json.dumps({"player_name": p.short_name or p.name})
                )
                self.session.add(new_saga)
                self._create_news(season_year, matchday, 
                    f"Rumours: {p.name} unsettled?", 
                    f"Sources close to {p.name} suggest the player is increasingly unhappy at {p.club.name}.",
                    "transfer"
                )
        
        # 2. Contract Standoff Trigger
        # Star players with expiring contracts (next season or current)
        stars_with_expiring_contract = (
            self.session.query(Player)
            .filter(Player.overall >= 75)
            .filter(Player.club_id.isnot(None))
            .filter(Player.contract_expiry <= season_year + 1)
            .all()
        )
        for p in stars_with_expiring_contract:
            existing = self.session.query(Saga).filter_by(target_id=p.id, type="contract_standoff", is_active=True).first()
            if not existing and random.random() < 0.15:
                new_saga = Saga(
                    type="contract_standoff",
                    target_id=p.id,
                    club_id=p.club_id,
                    stage=1,
                    data=json.dumps({"player_name": p.short_name or p.name, "expiry": p.contract_expiry})
                )
                self.session.add(new_saga)
                self._create_news(season_year, matchday,
                    f"Contract talks stall for {p.short_name or p.name}",
                    f"{p.club.name} are reportedly struggling to reach an agreement with {p.name} over a new contract.",
                    "finance"
                )

    def _handle_transfer_saga(self, saga: Saga, season_year: int, matchday: int):
        player = self.session.query(Player).get(saga.target_id)
        if not player or player.morale > 60:
            saga.is_active = False
            return
            
        # Realism Spike: If player is seriously injured, the transfer saga dies down
        if (player.injured_weeks or 0) >= 2:
            saga.is_active = False
            self._create_news(season_year, matchday, 
                f"Transfer talk cools for {player.short_name or player.name}", 
                f"With {player.name} sidelined through injury, rumors of a move away from {player.club.name} have dissipated.",
                "transfer"
            )
            return

        data = json.loads(saga.data)
        name = data["player_name"]

        if saga.stage == 1 and random.random() < 0.3:
            # Stage 2: Agent Leaks
            saga.stage = 2
            self._create_news(season_year, matchday,
                f"Agent speaks out on {name} future",
                f"The agent of {name} has refused to rule out a move away from {player.club.name} this summer.",
                "transfer"
            )
        elif saga.stage == 2 and random.random() < 0.2:
            # Stage 3: Public Unrest
            saga.stage = 3
            player.wants_transfer = True
            self._create_news(season_year, matchday,
                f"{name} hands in transfer request!",
                f"In a shocking development, {name} has formally requested a transfer from {player.club.name}.",
                "transfer"
            )

    def _handle_contract_saga(self, saga: Saga, season_year: int, matchday: int):
        player = self.session.query(Player).get(saga.target_id)
        if not player or player.contract_expiry > season_year + 1:
            saga.is_active = False
            return

        data = json.loads(saga.data)
        name = data["player_name"]

        if saga.stage == 1 and random.random() < 0.25:
            # Stage 2: Agent demands
            saga.stage = 2
            self._create_news(season_year, matchday,
                f"Agent: {name} deserves 'World Class' terms",
                f"The representative of {name} has publicly stated that the player expects a significant wage increase to reflect his status at {player.club.name}.",
                "finance"
            )
        elif saga.stage == 2 and random.random() < 0.15:
            # Stage 3: Training Boycott / Fallout
            saga.stage = 3
            player.morale = max(0, (player.morale or 65.0) - 25)
            player.loyalty_to_manager = max(0, (player.loyalty_to_manager or 50.0) - 20)
            self._create_news(season_year, matchday,
                f"Fallout: {name} misses training!",
                f"{name} has reportedly missed training this morning as the contract standoff at {player.club.name} reaches a boiling point.",
                "general"
            )
        elif saga.stage == 3 and random.random() < 0.1:
            # Outcome: Transfer request if still stuck
            saga.is_active = False
            player.wants_transfer = True
            self._create_news(season_year, matchday,
                f"{name} reaches point of no return",
                f"Following the contract dispute, {name} has informed {player.club.name} that he will not sign a new deal and wishes to leave.",
                "transfer"
            )

    def _create_news(self, season: int, matchday: int, headline: str, body: str, category: str):
        news = NewsItem(
            season=season,
            matchday=matchday,
            headline=headline,
            body=body,
            category=category
        )
        self.session.add(news)
