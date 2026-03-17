"""Database connection and session management."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from fm.db.models import Base

_engine = None
_SessionFactory = None


def get_engine(db_path: str | Path | None = None):
    """Return (or create) the global SQLAlchemy engine."""
    global _engine
    if _engine is None:
        if db_path is None:
            from fm.config import SAVE_DIR, DB_NAME
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            db_path = SAVE_DIR / DB_NAME
        uri = f"sqlite:///{db_path}"
        _engine = create_engine(uri, echo=False, future=True)
        # Enable WAL mode for better concurrent read performance
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return _engine


def init_db(db_path: str | Path | None = None) -> None:
    """Create all tables if they don't exist."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)


def reset_db(db_path: str | Path | None = None) -> None:
    """Drop and recreate all tables (destructive)."""
    engine = get_engine(db_path)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Return a new database session."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory()


def close_engine() -> None:
    """Dispose the global engine (for clean shutdown)."""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _SessionFactory = None
