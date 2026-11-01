"""Group CRUD, membership, scope grants, and depth-1 parent validation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Group, Scope, User, group_scope, user_group
from app.services.audit import record
from app.services.errors import (
    DuplicateGroupName,
    GroupHierarchyError,
    GroupNotFound,
    ScopeNotFound,
    UserNotFound,
)


def create_group(
    db: Session,
    *,
    realm_id: int,
    name: str,
    description: str | None = None,
    parent_group_id: int | None = None,
) -> Group:
    name = name.strip()
    if not name:
        raise ValueError("group name must be non-empty")

    existing = db.execute(
        select(Group).where(Group.realm_id == realm_id, Group.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateGroupName(name)

    if parent_group_id is not None:
        _validate_parent(db, group_id=None, parent_group_id=parent_group_id)

    group = Group(
        realm_id=realm_id,
        name=name,
        description=description,
        parent_group_id=parent_group_id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    record("group.created", group_id=group.id, name=group.name)
    return group


def get_group(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise GroupNotFound(group_id)
    return group


def list_groups(db: Session, *, realm_id: int) -> list[Group]:
    return list(
        db.execute(select(Group).where(Group.realm_id == realm_id).order_by(Group.name)).scalars()
    )


def delete_group(db: Session, group_id: int) -> None:
    group = get_group(db, group_id)
    db.delete(group)
    db.commit()
    record("group.deleted", group_id=group_id)


def set_parent_group(db: Session, group_id: int, parent_group_id: int | None) -> Group:
    group = get_group(db, group_id)
    if parent_group_id is not None:
        _validate_parent(db, group_id=group_id, parent_group_id=parent_group_id)
    group.parent_group_id = parent_group_id
    db.commit()
    db.refresh(group)
    record("group.parent_set", group_id=group_id, parent_group_id=parent_group_id)
    return group


def _validate_parent(db: Session, *, group_id: int | None, parent_group_id: int) -> None:
    """Enforce depth-1 hierarchy (§7 trade-off #4).

    Rules:
    - parent must exist
    - parent must not be the group itself
    - parent must not already have a parent (that would be depth 2)
    - the group (if existing) must not have children (that would be depth 2)
    """
    parent = db.get(Group, parent_group_id)
    if parent is None:
        raise GroupNotFound(parent_group_id)
    if group_id is not None and parent.id == group_id:
        raise GroupHierarchyError("a group cannot be its own parent")
    if parent.parent_group_id is not None:
        raise GroupHierarchyError("parent group already has a parent (max depth 1)")
    if group_id is not None:
        has_children = db.execute(
            select(Group.id).where(Group.parent_group_id == group_id).limit(1)
        ).scalar_one_or_none()
        if has_children is not None:
            raise GroupHierarchyError("group already has children (max depth 1)")


# ---------- membership ----------

def add_member(db: Session, *, group_id: int, user_id: int) -> None:
    get_group(db, group_id)
    if db.get(User, user_id) is None:
        raise UserNotFound(user_id)

    already = db.execute(
        select(user_group.c.user_id).where(
            user_group.c.group_id == group_id, user_group.c.user_id == user_id
        )
    ).scalar_one_or_none()
    if already is not None:
        return  # idempotent

    db.execute(user_group.insert().values(group_id=group_id, user_id=user_id))
    db.commit()
    record("group.member_added", group_id=group_id, user_id=user_id)


def remove_member(db: Session, *, group_id: int, user_id: int) -> None:
    get_group(db, group_id)
    db.execute(
        user_group.delete().where(
            user_group.c.group_id == group_id, user_group.c.user_id == user_id
        )
    )
    db.commit()
    record("group.member_removed", group_id=group_id, user_id=user_id)


# ---------- scope grants ----------

def grant_scope_to_group(db: Session, *, group_id: int, scope_id: int) -> None:
    get_group(db, group_id)
    if db.get(Scope, scope_id) is None:
        raise ScopeNotFound(scope_id)

    already = db.execute(
        select(group_scope.c.scope_id).where(
            group_scope.c.group_id == group_id, group_scope.c.scope_id == scope_id
        )
    ).scalar_one_or_none()
    if already is not None:
        return

    db.execute(group_scope.insert().values(group_id=group_id, scope_id=scope_id))
    db.commit()
    record("group.scope_granted", group_id=group_id, scope_id=scope_id)


def revoke_scope_from_group(db: Session, *, group_id: int, scope_id: int) -> None:
    get_group(db, group_id)
    db.execute(
        group_scope.delete().where(
            group_scope.c.group_id == group_id, group_scope.c.scope_id == scope_id
        )
    )
    db.commit()
    record("group.scope_revoked", group_id=group_id, scope_id=scope_id)