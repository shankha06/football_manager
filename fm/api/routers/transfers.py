"""Transfer market endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.api.schemas.common import PlayerBrief
from fm.api.schemas.transfers import (
    TransferBidCreate,
    TransferBidResponse,
    TransferMarketPlayer,
    TransferSearch,
)
from fm.db.models import Club, Player, Season, TransferBid
from fm.world.transfer_market import TransferMarket

router = APIRouter()


@router.get("/market", response_model=list[TransferMarketPlayer])
def search_market(
    position: str | None = None,
    min_overall: int | None = None,
    max_value: float | None = None,
    max_age: int | None = None,
    min_age: int | None = None,
    nationality: str | None = None,
    free_agents_only: bool = False,
    max_results: int = Query(default=50, le=200),
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Search the transfer market with optional filters."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    tm = TransferMarket(session)
    players = tm.search_players(
        position=position,
        min_overall=min_overall or 0,
        max_value=max_value or 999.0,
        exclude_club_id=season.human_club_id,
        max_age=max_age,
        min_age=min_age,
        nationality=nationality,
        free_agents_only=free_agents_only,
        max_results=max_results,
    )

    results = []
    for p in players:
        club_name = None
        if p.club_id:
            club = session.get(Club, p.club_id)
            if club:
                club_name = club.name

        results.append(
            TransferMarketPlayer(
                player=PlayerBrief(
                    id=p.id,
                    name=p.name,
                    position=p.position,
                    overall=p.overall,
                    age=p.age,
                    nationality=p.nationality,
                    club_id=p.club_id,
                ),
                market_value=p.market_value or 0.0,
                wage=p.wage or 0.0,
                contract_expiry=p.contract_expiry,
                club_name=club_name,
                asking_price=tm.calculate_market_value(p) if hasattr(tm, "calculate_market_value") else None,
            )
        )

    return results


@router.post("/bid", response_model=TransferBidResponse)
def place_bid(
    body: TransferBidCreate,
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Place a transfer bid for a player."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    player = session.get(Player, body.player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found.")

    # Create the bid record
    bid = TransferBid(
        player_id=body.player_id,
        bidding_club_id=season.human_club_id,
        selling_club_id=player.club_id,
        bid_amount=body.bid_amount,
        offered_wage=body.offered_wage or 0.0,
        offered_contract_years=body.offered_contract_years,
        status="pending",
        season=season.year,
        is_loan_bid=body.is_loan_bid,
        sell_on_pct=body.sell_on_pct,
    )
    session.add(bid)
    session.flush()

    # Attempt to process the bid via TransferMarket
    tm = TransferMarket(session)
    accepted = tm.make_bid(
        buyer_club_id=season.human_club_id,
        player_id=body.player_id,
        bid_amount=body.bid_amount,
        season=season.year,
    )

    bid.status = "accepted" if accepted else "rejected"
    session.commit()
    session.refresh(bid)

    return TransferBidResponse(
        id=bid.id,
        player_id=bid.player_id,
        player_name=player.name,
        bidding_club_id=bid.bidding_club_id,
        selling_club_id=bid.selling_club_id,
        bid_amount=bid.bid_amount,
        status=bid.status,
        counter_amount=bid.counter_amount,
    )


@router.get("/bids", response_model=list[TransferBidResponse])
def list_bids(
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """List all active/recent bids for the human club."""
    if season.human_club_id is None:
        raise HTTPException(status_code=400, detail="No human club set.")

    bids = (
        session.query(TransferBid)
        .filter_by(bidding_club_id=season.human_club_id, season=season.year)
        .order_by(TransferBid.id.desc())
        .all()
    )

    results = []
    for b in bids:
        player = session.get(Player, b.player_id)
        results.append(
            TransferBidResponse(
                id=b.id,
                player_id=b.player_id,
                player_name=player.name if player else None,
                bidding_club_id=b.bidding_club_id,
                selling_club_id=b.selling_club_id,
                bid_amount=b.bid_amount,
                status=b.status,
                counter_amount=b.counter_amount,
            )
        )

    return results
