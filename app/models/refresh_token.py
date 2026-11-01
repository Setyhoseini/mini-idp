"""Refresh token — long-lived, rotated on each use."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAtMixin
from app.db import UTCDateTime

if TYPE_CHECKING:
    from app.models.client import Client
    from app.models.user import User
    from app.models.session import UserSession


class RefreshToken(Base, CreatedAtMixin):
    __tablename__ = "refresh_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    # NOTE: `client_id` here is the FK to client.id (int PK). See report §3.
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id", ondelete="CASCADE"), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    rotated_from: Mapped[int | None] = mapped_column(
        ForeignKey("refresh_token.id", ondelete="SET NULL"), nullable=True
    )

    client: Mapped[Client] = relationship()
    user: Mapped[User] = relationship()
    session: Mapped[UserSession] = relationship()
    previous: Mapped[RefreshToken | None] = relationship(remote_side="RefreshToken.id")