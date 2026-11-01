"""Client — an OAuth2/OIDC client application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin

if TYPE_CHECKING:
    from app.models.realm import Realm


class Client(Base, CreatedAtMixin):
    __tablename__ = "client"
    __table_args__ = (
        UniqueConstraint("realm_id", "client_id", name="uq_client_realm_id_client_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    realm_id: Mapped[int] = mapped_column(ForeignKey("realm.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable: public clients authenticate via PKCE only (no shared secret).
    client_secret_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    redirect_uris: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    post_logout_redirect_uris: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allowed_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    realm: Mapped[Realm] = relationship(back_populates="clients")