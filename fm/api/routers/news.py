"""News feed endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from fm.api.dependencies import get_db_session, get_current_season
from fm.api.schemas.common import PaginatedResponse
from fm.db.models import NewsItem, Season

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────


class NewsItemSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    season: int
    matchday: int | None = None
    headline: str
    body: str | None = None
    category: str
    is_read: bool


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/", response_model=PaginatedResponse[NewsItemSchema])
def get_news(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    category: str | None = None,
    unread_only: bool = False,
    session: Session = Depends(get_db_session),
    season: Season = Depends(get_current_season),
):
    """Get news items with pagination and optional filters."""
    query = (
        session.query(NewsItem)
        .filter_by(season=season.year)
    )

    if category:
        query = query.filter_by(category=category)
    if unread_only:
        query = query.filter_by(is_read=False)

    total = query.count()
    items = (
        query.order_by(NewsItem.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return PaginatedResponse(
        items=[NewsItemSchema.model_validate(item) for item in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/{news_id}/read", status_code=204)
def mark_news_read(
    news_id: int,
    session: Session = Depends(get_db_session),
):
    """Mark a news item as read."""
    item = session.get(NewsItem, news_id)
    if item is None:
        raise HTTPException(status_code=404, detail="News item not found.")

    item.is_read = True
    session.commit()
