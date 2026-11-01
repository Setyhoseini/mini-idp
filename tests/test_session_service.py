"""Session service tests: creation, lookup, expiry, revocation."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import UserSession
from app.services import session_service, user_service


def _alice(db, realm):
    return user_service.create_user(
        db, realm_id=realm.id, username="alice", password="password-123"
    )


def test_login_creates_session(db_session: Session, realm) -> None:
    user_service.create_user(db_session, realm_id=realm.id, username="alice", password="password-123")
    result = session_service.attempt_login(
        db_session,
        username="alice",
        password="password-123",
        user_agent="test-agent",
        ip="127.0.0.1",
        ttl_seconds=3600,
    )
    assert result is not None
    assert result.user.username == "alice"
    assert result.raw_token
    # Round-trip: the raw token should resolve back to the session.
    session = session_service.get_active_session_by_token(db_session, result.raw_token)
    assert session is not None and session.id == result.session.id


def test_login_wrong_password_returns_none(db_session: Session, realm) -> None:
    user_service.create_user(db_session, realm_id=realm.id, username="alice", password="password-123")
    result = session_service.attempt_login(
        db_session,
        username="alice",
        password="wrong",
        user_agent=None,
        ip=None,
        ttl_seconds=3600,
    )
    assert result is None


def test_login_unknown_user_returns_none(db_session: Session) -> None:
    result = session_service.attempt_login(
        db_session,
        username="nobody",
        password="password-123",
        user_agent=None,
        ip=None,
        ttl_seconds=3600,
    )
    assert result is None


def test_login_disabled_user_returns_none(db_session: Session, realm) -> None:
    u = user_service.create_user(db_session, realm_id=realm.id, username="alice", password="password-123")
    user_service.disable_user(db_session, u.id)
    result = session_service.attempt_login(
        db_session,
        username="alice",
        password="password-123",
        user_agent=None,
        ip=None,
        ttl_seconds=3600,
    )
    assert result is None


def test_expired_session_is_not_returned(db_session: Session, realm) -> None:
    user_service.create_user(db_session, realm_id=realm.id, username="alice", password="password-123")
    # TTL of 1 ms — the session will be expired immediately after creation.
    result = session_service.attempt_login(
        db_session,
        username="alice",
        password="password-123",
        user_agent=None,
        ip=None,
        ttl_seconds=0,
    )
    time.sleep(0.01)
    assert session_service.get_active_session_by_token(db_session, result.raw_token) is None


def test_revoked_session_is_not_returned(db_session: Session, realm) -> None:
    user_service.create_user(db_session, realm_id=realm.id, username="alice", password="password-123")
    result = session_service.attempt_login(
        db_session,
        username="alice",
        password="password-123",
        user_agent=None,
        ip=None,
        ttl_seconds=3600,
    )
    session_service.revoke_session(db_session, result.session.id)
    assert session_service.get_active_session_by_token(db_session, result.raw_token) is None


def test_revoke_is_idempotent(db_session: Session, realm) -> None:
    user_service.create_user(db_session, realm_id=realm.id, username="alice", password="password-123")
    result = session_service.attempt_login(
        db_session,
        username="alice",
        password="password-123",
        user_agent=None,
        ip=None,
        ttl_seconds=3600,
    )
    session_service.revoke_session(db_session, result.session.id)
    session_service.revoke_session(db_session, result.session.id)  # no-op, no raise
    assert session_service.get_active_session_by_token(db_session, result.raw_token) is None


def test_unknown_token_returns_none(db_session: Session) -> None:
    assert session_service.get_active_session_by_token(db_session, "nonexistent") is None
    assert session_service.get_active_session_by_token(db_session, "") is None