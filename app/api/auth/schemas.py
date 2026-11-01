"""Request/response schemas for the auth surface."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=512)


class SessionUser(BaseModel):
    id: int
    username: str
    email: str | None = None


class SessionInfoResponse(BaseModel):
    authenticated: bool
    user: SessionUser | None = None
    session_exp: int | None = None  # unix timestamp (seconds)


class LoginResponse(BaseModel):
    user: SessionUser
    session_exp: int