"""Database engine and session factory.

Reads ``DATABASE_URL`` from the environment. Supports SQLite (local dev) and
Postgres (production). The engine is created lazily so tests can override the
URL before the first call.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _engine_kwargs(database_url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"future": True}
    if database_url.startswith("sqlite"):
        # Allow connections from FastAPI's threadpool
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Pool tuning suitable for Render free tier + Neon
        kwargs["pool_pre_ping"] = True
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 5
    return kwargs


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first call."""
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get("DATABASE_URL", "sqlite:///./dev.db")
        _engine = create_engine(url, **_engine_kwargs(url))
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
        if url.startswith("sqlite"):
            _install_sqlite_pragmas(_engine)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide sessionmaker, creating it on first call."""
    if _SessionLocal is None:
        get_engine()  # initializes both
    assert _SessionLocal is not None
    return _SessionLocal


def reset_engine() -> None:
    """Forget the cached engine. Tests call this when overriding ``DATABASE_URL``."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and closes it after the request."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _install_sqlite_pragmas(engine: Engine) -> None:
    """Turn on FK enforcement for SQLite (off by default)."""

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
