"""Typed application configuration.

Reads values from environment variables and, if present, a `.env` file
in the current working directory. See `.env.example` for the full list.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "mini-idp"
    environment: str = "development"
    debug: bool = True

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Issuer — used as `iss` claim and as `issuer` in discovery document
    issuer: str = "http://localhost:8000"

    # Database
    database_url: str = "sqlite:///./mini_idp.db"

    # Realm
    realm_name: str = "main"

    # RSA keys
    private_key_path: str = "./keys/private.pem"
    public_key_path: str = "./keys/public.pem"

    # TTLs (seconds)
    access_token_ttl_seconds: int = 600
    id_token_ttl_seconds: int = 300
    refresh_token_ttl_seconds: int = 14 * 24 * 3600
    authorization_code_ttl_seconds: int = 60
    session_ttl_seconds: int = 8 * 3600

    # Session cookie
    session_cookie_name: str = "SID"
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"

    # Login rate limiting
    login_rate_limit_per_minute: int = 10


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide singleton Settings instance.

    Cached so the .env file is parsed once. Tests that need a fresh
    instance can call `get_settings.cache_clear()`.
    """
    return Settings()