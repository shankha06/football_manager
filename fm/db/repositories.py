"""Repository pattern for database access with eager loading."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from fm.db.models import (
    Club,
    Contract,
    Fixture,
    League,
    LeagueStanding,
    Player,
    PlayerStats,
)


class PlayerRepository:
    """Data-access helpers for :class:`Player` entities."""

    @staticmethod
    def get_squad(session: Session, club_id: int) -> list[Player]:
        """Return all players for *club_id* with contracts and stats eagerly loaded."""
        stmt = (
            select(Player)
            .where(Player.club_id == club_id)
            .options(
                selectinload(Player.contracts),
                selectinload(Player.stats),
            )
        )
        return list(session.scalars(stmt).all())

    @staticmethod
    def get_by_id(session: Session, player_id: int) -> Player | None:
        """Return a single player by primary key, or ``None``."""
        stmt = (
            select(Player)
            .where(Player.id == player_id)
            .options(
                selectinload(Player.contracts),
                selectinload(Player.stats),
            )
        )
        return session.scalars(stmt).first()

    @staticmethod
    def get_free_agents(session: Session) -> list[Player]:
        """Return all players without a club."""
        stmt = (
            select(Player)
            .where(Player.club_id.is_(None))
            .options(selectinload(Player.stats))
        )
        return list(session.scalars(stmt).all())

    @staticmethod
    def search(session: Session, filters: dict[str, Any]) -> list[Player]:
        """Search players by arbitrary filters.

        Supported filter keys:
        - ``min_overall`` / ``max_overall`` (int)
        - ``position`` (str)
        - ``nationality`` (str)
        - ``name`` (str, case-insensitive LIKE)
        - ``max_age`` / ``min_age`` (int)
        - ``club_id`` (int or None for free agents)
        """
        stmt = select(Player).options(selectinload(Player.stats))

        if "min_overall" in filters:
            stmt = stmt.where(Player.overall >= filters["min_overall"])
        if "max_overall" in filters:
            stmt = stmt.where(Player.overall <= filters["max_overall"])
        if "position" in filters:
            stmt = stmt.where(Player.position == filters["position"])
        if "nationality" in filters:
            stmt = stmt.where(Player.nationality == filters["nationality"])
        if "name" in filters:
            stmt = stmt.where(Player.name.ilike(f"%{filters['name']}%"))
        if "min_age" in filters:
            stmt = stmt.where(Player.age >= filters["min_age"])
        if "max_age" in filters:
            stmt = stmt.where(Player.age <= filters["max_age"])
        if "club_id" in filters:
            if filters["club_id"] is None:
                stmt = stmt.where(Player.club_id.is_(None))
            else:
                stmt = stmt.where(Player.club_id == filters["club_id"])

        return list(session.scalars(stmt).all())

    @staticmethod
    def bulk_update(session: Session, players: list[Player]) -> None:
        """Merge a batch of player instances into the session."""
        for player in players:
            session.merge(player)


class ClubRepository:
    """Data-access helpers for :class:`Club` entities."""

    @staticmethod
    def get_by_id(session: Session, club_id: int) -> Club | None:
        """Return a single club by primary key, or ``None``."""
        stmt = (
            select(Club)
            .where(Club.id == club_id)
            .options(
                selectinload(Club.players),
                selectinload(Club.standings),
                selectinload(Club.manager),
                selectinload(Club.tactical_setup),
            )
        )
        return session.scalars(stmt).first()

    @staticmethod
    def get_all_with_standings(session: Session, season: int) -> list[Club]:
        """Return every club that has a league standing for *season*."""
        stmt = (
            select(Club)
            .join(Club.standings)
            .where(LeagueStanding.season == season)
            .options(
                selectinload(Club.standings),
                selectinload(Club.players),
            )
        )
        return list(session.scalars(stmt).unique().all())

    @staticmethod
    def get_league_clubs(session: Session, league_id: int) -> list[Club]:
        """Return all clubs belonging to a given league."""
        stmt = (
            select(Club)
            .where(Club.league_id == league_id)
            .options(
                selectinload(Club.players),
                selectinload(Club.standings),
            )
        )
        return list(session.scalars(stmt).all())


class FixtureRepository:
    """Data-access helpers for :class:`Fixture` entities."""

    @staticmethod
    def get_matchday_fixtures(
        session: Session, season: int, matchday: int
    ) -> list[Fixture]:
        """Return all fixtures for a specific matchday in a season."""
        stmt = (
            select(Fixture)
            .where(Fixture.season == season, Fixture.matchday == matchday)
            .options(
                joinedload(Fixture.home_club),
                joinedload(Fixture.away_club),
            )
        )
        return list(session.scalars(stmt).unique().all())

    @staticmethod
    def get_club_fixtures(
        session: Session, club_id: int, season: int
    ) -> list[Fixture]:
        """Return all fixtures (played and unplayed) for a club in a season."""
        stmt = (
            select(Fixture)
            .where(
                Fixture.season == season,
                (Fixture.home_club_id == club_id) | (Fixture.away_club_id == club_id),
            )
            .order_by(Fixture.matchday)
            .options(
                joinedload(Fixture.home_club),
                joinedload(Fixture.away_club),
            )
        )
        return list(session.scalars(stmt).unique().all())

    @staticmethod
    def get_results(
        session: Session, season: int, played_only: bool = True
    ) -> list[Fixture]:
        """Return fixtures for a season, optionally filtered to played only."""
        stmt = (
            select(Fixture)
            .where(Fixture.season == season)
            .options(
                joinedload(Fixture.home_club),
                joinedload(Fixture.away_club),
            )
        )
        if played_only:
            stmt = stmt.where(Fixture.played.is_(True))
        stmt = stmt.order_by(Fixture.matchday)
        return list(session.scalars(stmt).unique().all())
