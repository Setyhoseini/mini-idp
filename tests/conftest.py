"""Shared pytest fixtures."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session as OrmSession, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  — registers all models with Base.metadata
from app.db import Base

import pytest as _pytest

from app.models import Realm, Scope, User
from app.services import group_service, realm_service, scope_service, user_service


@pytest.fixture
def db_session() -> OrmSession:
    """A fresh in-memory SQLite database for each test.

    - StaticPool keeps a single shared connection across threads (needed
      because FastAPI runs sync route handlers in a worker threadpool).
    - check_same_thread=False tells the sqlite3 driver that cross-thread
      use is intentional.
    - The connect listener enables FK enforcement, matching app.db's
      runtime behavior.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_pragma(dbapi_conn, _record) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()

@pytest.fixture
def realm(db_session) -> Realm:
    return realm_service.get_or_create_realm(db_session, "main")


@pytest.fixture
def admin_scope(db_session, realm) -> Scope:
    return scope_service.create_scope(db_session, realm_id=realm.id, name="admin")


@pytest.fixture
def admin_user(db_session, realm, admin_scope) -> User:
    u = user_service.create_user(
        db_session, realm_id=realm.id, username="admin", password="admin-pass-123"
    )
    user_service.grant_scope_to_user(db_session, user_id=u.id, scope_id=admin_scope.id)
    return u        