"""Request and response schemas for the admin surface."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateUserRequest(BaseModel):
    username: str = Field(..., max_length=128)
    password: str = Field(..., min_length=8, max_length=512)
    email: str | None = Field(default=None, max_length=255)
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)

    @field_validator("username")
    @classmethod
    def _non_blank_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("username must be non-empty")
        return v


class UserResponse(BaseModel):
    """Allowlist of user fields safe to expose over HTTP.

    Intentionally does NOT include `password_hash`, `realm_id`, or the
    internal `created_at`/`updated_at` — these are internal columns.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str | None
    first_name: str | None
    last_name: str | None
    enabled: bool


class EffectiveScopesResponse(BaseModel):
    user_id: int
    username: str
    scopes: list[str]