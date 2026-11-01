"""User CRUD, password management, and direct scope grants."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scope, User, user_scope
from app.security.passwords import hash_password
from app.services.audit import record
from app.services.errors import (
    DuplicateUsername,
    ScopeNotFound,
    UserNotFound,
    WeakPassword,
)

_UNSET = object()  # sentinel for optional PATCH-style updates
_MIN_PASSWORD_LEN = 8


def create_user(
    db: Session,
    *,
    realm_id: int,
    username: str,
    password: str,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    enabled: bool = True,
) -> User:
    username = username.strip()
    if not username:
        raise ValueError("username must be non-empty")
    if len(password) < _MIN_PASSWORD_LEN:
        raise WeakPassword(f"must be at least {_MIN_PASSWORD_LEN} characters")

    existing = db.execute(
        select(User).where(User.realm_id == realm_id, User.username == username)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateUsername(username)

    user = User(
        realm_id=realm_id,
        username=username,
        password_hash=hash_password(password),
        email=email,
        first_name=first_name,
        last_name=last_name,
        enabled=enabled,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record("user.created", actor_id=None, user_id=user.id, username=user.username)
    return user


def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise UserNotFound(user_id)
    return user

def get_user_by_username(db: Session, *, realm_id: int, username: str) -> User:
    """Look up a user by their username within a realm."""
    user = db.execute(
        select(User).where(User.realm_id == realm_id, User.username == username)
    ).scalar_one_or_none()
    if user is None:
        raise UserNotFound(username)
    return user

def list_users(db: Session, *, realm_id: int, limit: int = 100, offset: int = 0) -> list[User]:
    return list(
        db.execute(
            select(User)
            .where(User.realm_id == realm_id)
            .order_by(User.username)
            .limit(limit)
            .offset(offset)
        ).scalars()
    )


def update_user(
    db: Session,
    user_id: int,
    *,
    email: object = _UNSET,
    first_name: object = _UNSET,
    last_name: object = _UNSET,
    enabled: object = _UNSET,
) -> User:
    user = get_user(db, user_id)
    if email is not _UNSET:
        user.email = email
    if first_name is not _UNSET:
        user.first_name = first_name
    if last_name is not _UNSET:
        user.last_name = last_name
    if enabled is not _UNSET:
        user.enabled = enabled
    db.commit()
    db.refresh(user)
    record("user.updated", user_id=user_id)
    return user


def set_password(db: Session, user_id: int, new_password: str) -> None:
    if len(new_password) < _MIN_PASSWORD_LEN:
        raise WeakPassword(f"must be at least {_MIN_PASSWORD_LEN} characters")
    user = get_user(db, user_id)
    user.password_hash = hash_password(new_password)
    db.commit()
    record("user.password_changed", user_id=user_id)


def disable_user(db: Session, user_id: int) -> User:
    return update_user(db, user_id, enabled=False)


# ---------- direct scope grants ----------

def grant_scope_to_user(
    db: Session, *, user_id: int, scope_id: int, granted_by: int | None = None
) -> None:
    user = get_user(db, user_id)
    if db.get(Scope, scope_id) is None:
        raise ScopeNotFound(scope_id)

    already = db.execute(
        select(user_scope.c.scope_id).where(
            user_scope.c.user_id == user_id, user_scope.c.scope_id == scope_id
        )
    ).scalar_one_or_none()
    if already is not None:
        return  # idempotent grant

    db.execute(
        user_scope.insert().values(user_id=user_id, scope_id=scope_id, granted_by=granted_by)
    )
    db.commit()
    # Refresh the ORM relationship so callers see the new grant immediately.
    db.refresh(user)
    record("user.scope_granted", actor_id=granted_by, user_id=user_id, scope_id=scope_id)


def revoke_scope_from_user(db: Session, *, user_id: int, scope_id: int) -> None:
    get_user(db, user_id)  # 404 if not found
    db.execute(
        user_scope.delete().where(
            user_scope.c.user_id == user_id, user_scope.c.scope_id == scope_id
        )
    )
    db.commit()
    record("user.scope_revoked", user_id=user_id, scope_id=scope_id)