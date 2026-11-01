"""Group — aggregates scopes and users. Optional one-level hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin, group_scope, user_group

if TYPE_CHECKING:
    from app.models.realm import Realm
    from app.models.user import User
    from app.models.scope import Scope


class Group(Base, CreatedAtMixin):
    __tablename__ = "group"
    __table_args__ = (
        UniqueConstraint("realm_id", "name", name="uq_group_realm_id_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    realm_id: Mapped[int] = mapped_column(ForeignKey("realm.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    parent_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("group.id", ondelete="SET NULL"), nullable=True
    )

    realm: Mapped[Realm] = relationship(back_populates="groups")
    parent: Mapped[Group | None] = relationship(remote_side="Group.id", back_populates="children")
    children: Mapped[list[Group]] = relationship(back_populates="parent")

    users: Mapped[list[User]] = relationship(
        secondary=user_group,
        back_populates="groups",
    )

    scopes: Mapped[list[Scope]] = relationship(
        secondary=group_scope,
        back_populates="groups",
        lazy="selectin",
    )