"""OIDC discovery and JWKS endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.security.jwt_signer import get_jwt_signer

router = APIRouter(tags=["oidc"])


@router.get("/.well-known/openid-configuration")
def discovery() -> dict:
    settings = get_settings()
    base = settings.issuer.rstrip("/")
    return {
        "issuer": settings.issuer,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "userinfo_endpoint": f"{base}/userinfo",
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "introspection_endpoint": f"{base}/introspect",
        "revocation_endpoint": f"{base}/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["openid", "profile", "email", "admin"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


@router.get("/.well-known/jwks.json")
def jwks() -> dict:
    return get_jwt_signer().jwks()