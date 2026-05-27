"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

# Ensure tests use an isolated SQLite file before db.session is first imported.
_TEST_DB_PATH = Path(__file__).parent / "_test.db"


@pytest.fixture(scope="session", autouse=True)
def _set_test_db_env() -> None:
    os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH.as_posix()}"


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """Fresh schema + open session per test. Drops and recreates all tables."""
    from db import Base
    from db.session import get_engine, get_sessionmaker, reset_engine

    reset_engine()
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()
    engine = get_engine()
    Base.metadata.create_all(engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        reset_engine()
        if _TEST_DB_PATH.exists():
            _TEST_DB_PATH.unlink()
