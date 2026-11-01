"""Scope — the authorization unit. Groups aggregate scopes; users can also
receive scopes directly. See §4.5 of the architecture document for the
effective-scope formula."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, group_scope, user_scope

if TYPE_CHECKING:
    from app.models.realm import Realm
    from app.models.user import User
    from app.models.group import Group


class Scope(Base, CreatedAtMixin):
    __tablename__ = "scope"
    __table_args__ = (
        UniqueConstraint("realm_id", "name", name="uq_scope_realm_id_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    realm_id: Mapped[int] = mapped_column(ForeignKey("realm.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    realm: Mapped[Realm] = relationship(back_populates="scopes")

    groups: Mapped[list[Group]] = relationship(
        secondary=group_scope,
        back_populates="scopes",
    )

    users_direct: Mapped[list[User]] = relationship(
        secondary=user_scope,
        primaryjoin="Scope.id == user_scope.c.scope_id",
        secondaryjoin="User.id == user_scope.c.user_id",
        back_populates="direct_scopes",
    )