"""Shared declarative base, column mixins, and association tables.

Every ORM model in `app.models.*` inherits from `Base`. The mixins
provide consistent `created_at` / `updated_at` columns. The three
`Table` objects (`user_group`, `user_scope`, `group_scope`) are the
join tables between users, groups, and scopes; they live here so any
model can import them without circular dependencies.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Table, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Re-export Base so all model modules import from one place.
__all__ = [
    "Base",
    "CreatedAtMixin",
    "TimestampMixin",
    "user_group",
    "user_scope",
    "group_scope",
]


class CreatedAtMixin:
    """Adds a `created_at` timestamp column with a server default."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    """Adds `created_at` and `updated_at` with an on-update trigger."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


user_group = Table(
    "user_group",
    Base.metadata,
    Column("user_id", ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", ForeignKey("group.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


user_scope = Table(
    "user_scope",
    Base.metadata,
    Column("user_id", ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("scope_id", ForeignKey("scope.id", ondelete="CASCADE"), primary_key=True),
    # Who granted the scope — nullable because the seed system may not have a granter.
    Column("granted_by", ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


group_scope = Table(
    "group_scope",
    Base.metadata,
    Column("group_id", ForeignKey("group.id", ondelete="CASCADE"), primary_key=True),
    Column("scope_id", ForeignKey("scope.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)