"""Resource-server settings. Reads from the same .env as the IdP."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class RSSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "mini-idp-demo-resource"
    issuer: str = "http://localhost:8000"  # same env var as the IdP

    @property
    def jwks_uri(self) -> str:
        return f"{self.issuer.rstrip('/')}/.well-known/jwks.json"


@lru_cache
def get_rs_settings() -> RSSettings:
    return RSSettings()