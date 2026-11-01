"""User — an identity within a realm."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, user_group, user_scope

if TYPE_CHECKING:
    from app.models.realm import Realm
    from app.models.group import Group
    from app.models.scope import Scope


class User(Base, TimestampMixin):
    __tablename__ = "user"
    __table_args__ = (
        UniqueConstraint("realm_id", "username", name="uq_user_realm_id_username"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    realm_id: Mapped[int] = mapped_column(ForeignKey("realm.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    realm: Mapped[Realm] = relationship(back_populates="users")

    groups: Mapped[list[Group]] = relationship(
        secondary=user_group,
        back_populates="users",
        lazy="selectin",
    )

    direct_scopes: Mapped[list[Scope]] = relationship(
        secondary=user_scope,
        primaryjoin="User.id == user_scope.c.user_id",
        secondaryjoin="Scope.id == user_scope.c.scope_id",
        back_populates="users_direct",
        lazy="selectin",
    )