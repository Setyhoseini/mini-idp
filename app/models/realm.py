"""Realm — single-row in this project, modeled for future multi-tenancy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.group import Group
    from app.models.scope import Scope
    from app.models.client import Client


class Realm(Base, CreatedAtMixin):
    __tablename__ = "realm"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    groups: Mapped[list[Group]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    scopes: Mapped[list[Scope]] = relationship(back_populates="realm", cascade="all, delete-orphan")
    clients: Mapped[list[Client]] = relationship(back_populates="realm", cascade="all, delete-orphan")