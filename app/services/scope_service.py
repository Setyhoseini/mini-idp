"""Scope CRUD. Scopes are the authorization unit (§3.2 of the design)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scope
from app.services.audit import record
from app.services.errors import DuplicateScopeName, ScopeNotFound


def create_scope(db: Session, *, realm_id: int, name: str, description: str | None = None) -> Scope:
    name = name.strip()
    if not name:
        raise ValueError("scope name must be non-empty")

    existing = db.execute(
        select(Scope).where(Scope.realm_id == realm_id, Scope.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateScopeName(name)

    scope = Scope(realm_id=realm_id, name=name, description=description)
    db.add(scope)
    db.commit()
    db.refresh(scope)
    record("scope.created", scope_id=scope.id, name=scope.name)
    return scope


def get_scope(db: Session, scope_id: int) -> Scope:
    scope = db.get(Scope, scope_id)
    if scope is None:
        raise ScopeNotFound(scope_id)
    return scope


def list_scopes(db: Session, *, realm_id: int) -> list[Scope]:
    return list(
        db.execute(select(Scope).where(Scope.realm_id == realm_id).order_by(Scope.name)).scalars()
    )


def delete_scope(db: Session, scope_id: int) -> None:
    scope = get_scope(db, scope_id)
    db.delete(scope)
    db.commit()
    record("scope.deleted", scope_id=scope_id)