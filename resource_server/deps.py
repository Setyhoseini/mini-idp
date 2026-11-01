"""Bearer verification and scope enforcement for the resource server."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

import jwt
from fastapi import Depends, Header

from resource_server.errors import forbidden, unauthorized
from resource_server.settings import get_rs_settings


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_rs_settings().jwks_uri, cache_keys=True)


def get_jwks_client() -> jwt.PyJWKClient:
    """Dependency returning the JWKS client. Overridable in tests."""
    return _jwks_client()


def verify_bearer(
    authorization: str | None = Header(default=None),
    jwks_client: jwt.PyJWKClient = Depends(get_jwks_client),
) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized("invalid_request", "missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=get_rs_settings().issuer,
            options={
                "require": ["exp", "iat", "sub"],
                # See architecture §9.15: aud=client_id in this demo; the RS
                # cannot know every client, so aud is not enforced. iss + exp
                # are enforced. Documented trade-off.
                "verify_aud": False,
            },
        )
    except jwt.ExpiredSignatureError:
        raise unauthorized("invalid_token", "token has expired") from None
    except jwt.InvalidTokenError as exc:
        raise unauthorized("invalid_token", f"token rejected: {exc}") from None


def require_scope(required: str) -> Callable[[dict], dict]:
    def _checker(claims: dict = Depends(verify_bearer)) -> dict:
        scopes = (claims.get("scope") or "").split()
        if required not in scopes:
            raise forbidden(
                "insufficient_scope", f"requires scope {required!r}"
            )
        return claims

    return _checker