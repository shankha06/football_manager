"""Pydantic schemas for transfer market endpoints."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from fm.api.schemas.common import PlayerBrief


class TransferSearch(BaseModel):
    """Query filters for searching the transfer market."""
    position: str | None = None
    min_overall: int | None = None
    max_value: float | None = None
    max_age: int | None = None
    min_age: int | None = None
    nationality: str | None = None
    free_agents_only: bool = False
    max_results: int = 50


class TransferBidCreate(BaseModel):
    """Request body for placing a transfer bid."""
    player_id: int
    bid_amount: float
    offered_wage: float | None = None
    offered_contract_years: int = 3
    is_loan_bid: bool = False
    sell_on_pct: float = 0.0


class TransferBidResponse(BaseModel):
    """Response from a bid submission."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    player_id: int
    player_name: str | None = None
    bidding_club_id: int
    selling_club_id: int | None = None
    bid_amount: float
    status: str  # pending, accepted, rejected, countered, withdrawn
    counter_amount: float | None = None


class TransferMarketPlayer(BaseModel):
    """Player listed on the transfer market with valuation info."""
    player: PlayerBrief
    market_value: float
    wage: float
    contract_expiry: int | None = None
    club_name: str | None = None
    asking_price: float | None = None
