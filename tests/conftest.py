"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession, sessionmaker

from app import models  # noqa: F401  — registers all models with Base.metadata
from app.db import Base


@pytest.fixture
def db_session() -> OrmSession:
    """A fresh in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()