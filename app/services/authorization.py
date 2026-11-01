"""Effective-scope resolver — the single source of truth for authorization.

Formula (design §4.5):

    effective_scopes(user) = direct_scopes(user)
                           ∪ ⋃ group_scopes(g)   for g in groups(user)
                           ∪ ⋃ parent_of(g).scopes  for g in groups(user)

Every authorization decision in the system — /authorize filtering, /token
`scope` claim, /userinfo, /admin/.../effective-scopes — MUST call this
function. It is the one place where the formula lives.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Group, User
from app.services.errors import UserNotFound


def compute_effective_scopes(db: Session, user_id: int) -> set[str]:
    user = db.execute(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.direct_scopes),
            selectinload(User.groups).selectinload(Group.scopes),
            selectinload(User.groups).joinedload(Group.parent).selectinload(Group.scopes),
        )
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    if user is None:
        raise UserNotFound(user_id)

    names: set[str] = {scope.name for scope in user.direct_scopes}
    for group in user.groups:
        names.update(scope.name for scope in group.scopes)
        if group.parent is not None:
            names.update(scope.name for scope in group.parent.scopes)
    return names