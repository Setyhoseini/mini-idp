"""SSO session lifecycle and login verification."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken, User, UserSession
from app.security.passwords import hash_password, verify_password

_TOKEN_BYTES = 32


@dataclass
class LoginResult:
    user: User
    session: UserSession
    raw_token: str  # never stored; only the hash is in the DB


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A valid Argon2 hash used to equalize timing on unknown usernames."""
    return hash_password("timing-equalization-dummy-password")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def attempt_login(
    db: Session,
    *,
    username: str,
    password: str,
    user_agent: str | None,
    ip: str | None,
    ttl_seconds: int,
) -> LoginResult | None:
    """Verify credentials and create a session. Returns None on any failure.

    Failure is intentionally generic: wrong password, unknown user, and
    disabled account all return None. The caller returns one error message
    so that timing and message reveal nothing about which case applied.
    """
    username = username.strip()
    user = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()

    if user is None:
        # Consume equivalent time so unknown-user looks like wrong-password.
        verify_password(password, _dummy_hash())
        return None

    if not verify_password(password, user.password_hash):
        return None

    if not user.enabled:
        return None

    now = _now()
    raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
    session = UserSession(
        user_id=user.id,
        realm_id=user.realm_id,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(seconds=ttl_seconds),
        last_activity_at=now,
        user_agent=user_agent,
        ip=ip,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return LoginResult(user=user, session=session, raw_token=raw_token)


def get_active_session_by_token(db: Session, raw_token: str) -> UserSession | None:
    """Return the session matching `raw_token` if not revoked and not expired."""
    if not raw_token:
        return None
    session = db.execute(
        select(UserSession).where(UserSession.token_hash == _hash_token(raw_token))
    ).scalar_one_or_none()
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at <= _now():
        return None
    return session


def revoke_session(db: Session, session_id: int) -> None:
    """Revoke the session and every refresh token derived from it.

    Idempotent: revoking an already-revoked session is a no-op.
    """
    session = db.get(UserSession, session_id)
    if session is None or session.revoked_at is not None:
        return
    now = _now()
    session.revoked_at = now
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()