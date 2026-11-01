"""Shared declarative base, column mixins, and association tables."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, ForeignKey, Table, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime

__all__ = [
    "Base",
    "CreatedAtMixin",
    "TimestampMixin",
    "user_group",
    "user_scope",
    "group_scope",
]


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.now(),
        nullable=False,
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


user_group = Table(
    "user_group",
    Base.metadata,
    Column("user_id", ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", ForeignKey("group.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", UTCDateTime, server_default=func.now(), nullable=False),
)


user_scope = Table(
    "user_scope",
    Base.metadata,
    Column("user_id", ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    Column("scope_id", ForeignKey("scope.id", ondelete="CASCADE"), primary_key=True),
    Column("granted_by", ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
    Column("created_at", UTCDateTime, server_default=func.now(), nullable=False),
)


group_scope = Table(
    "group_scope",
    Base.metadata,
    Column("group_id", ForeignKey("group.id", ondelete="CASCADE"), primary_key=True),
    Column("scope_id", ForeignKey("scope.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", UTCDateTime, server_default=func.now(), nullable=False),
)