"""In-memory cache of game entities for fast access during a season."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from fm.db.models import Club, Fixture, League, LeagueStanding, Player, Season

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class GameState:
    """Batch-loads clubs and players at season start, tracks dirty entities,
    and flushes only modified rows back to the database.
    """

    def __init__(self) -> None:
        self._clubs: dict[int, Club] = {}
        self._players: dict[int, Player] = {}
        self._season: Season | None = None
        self._dirty: set[tuple[str, int]] = set()

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def clubs(self) -> dict[int, Club]:
        return self._clubs

    @property
    def players(self) -> dict[int, Player]:
        return self._players

    @property
    def season(self) -> Season | None:
        return self._season

    @property
    def dirty_flags(self) -> set[tuple[str, int]]:
        return self._dirty

    # ── Loading ───────────────────────────────────────────────────────────

    def load_season(self, session: Session, season_year: int) -> None:
        """Eagerly load the full season state into memory.

        Parameters
        ----------
        session:
            An active SQLAlchemy session.
        season_year:
            The ``year`` column value on the :class:`Season` row.
        """
        # Season
        self._season = (
            session.query(Season).filter(Season.year == season_year).one()
        )

        # Clubs with related collections useful during a season tick
        clubs = (
            session.query(Club)
            .options(
                selectinload(Club.players),
                selectinload(Club.standings),
                selectinload(Club.tactical_setup),
                selectinload(Club.manager),
                selectinload(Club.contracts),
            )
            .all()
        )
        self._clubs = {c.id: c for c in clubs}

        # Players with stats and contracts eagerly loaded
        players = (
            session.query(Player)
            .options(
                selectinload(Player.stats),
                selectinload(Player.contracts),
            )
            .all()
        )
        self._players = {p.id: p for p in players}

        # Start with a clean dirty set
        self._dirty.clear()

    # ── Accessors ─────────────────────────────────────────────────────────

    def get_club(self, club_id: int) -> Club | None:
        """Return a club by id, or ``None`` if not loaded."""
        return self._clubs.get(club_id)

    def get_player(self, player_id: int) -> Player | None:
        """Return a player by id, or ``None`` if not loaded."""
        return self._players.get(player_id)

    def get_squad(self, club_id: int) -> list[Player]:
        """Return all players whose ``club_id`` matches *club_id*."""
        return [p for p in self._players.values() if p.club_id == club_id]

    # ── Dirty tracking ────────────────────────────────────────────────────

    def mark_dirty(self, entity_type: str, entity_id: int) -> None:
        """Flag an entity for write-back on the next :meth:`flush`."""
        self._dirty.add((entity_type, entity_id))

    def flush(self, session: Session) -> None:
        """Batch-write all dirty entities to the database and clear flags.

        The caller is responsible for calling ``session.commit()`` afterwards.
        """
        for entity_type, entity_id in self._dirty:
            if entity_type == "player":
                obj = self._players.get(entity_id)
            elif entity_type == "club":
                obj = self._clubs.get(entity_id)
            elif entity_type == "season" and self._season is not None:
                obj = self._season
            else:
                continue
            if obj is not None:
                session.merge(obj)
        self._dirty.clear()
