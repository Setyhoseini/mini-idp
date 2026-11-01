"""OAuth2 client authentication for /token, /introspect, /revoke."""

from __future__ import annotations

import base64

from fastapi import Request
from sqlalchemy.orm import Session

from app.api.exceptions import OAuthError
from app.models import Client
from app.security.passwords import verify_password
from app.services import client_service, realm_service


def _parse_basic(header: str | None) -> tuple[str, str] | None:
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header.split(" ", 1)[1]).decode()
        client_id, secret = raw.split(":", 1)
        return client_id, secret
    except Exception:
        return None


def resolve_client(
    db: Session,
    request: Request,
    client_id_form: str | None,
    client_secret_form: str | None = None,
) -> Client:
    """Authenticate a client via Basic header or form params (client_secret_post)."""
    basic = _parse_basic(request.headers.get("authorization"))
    if basic is not None:
        client_id, client_secret = basic
    elif client_id_form:
        client_id, client_secret = client_id_form, client_secret_form
    else:
        raise OAuthError(
            status_code=401,
            error="invalid_client",
            error_description="client authentication required",
        )

    realm = realm_service.get_single_realm(db)
    try:
        client = client_service.get_client_by_public_id(
            db, realm_id=realm.id, client_id=client_id
        )
    except Exception:
        raise OAuthError(
            status_code=401, error="invalid_client", error_description="unknown client"
        ) from None

    if not client.is_public:
        if not client_secret or not client.client_secret_hash:
            raise OAuthError(
                status_code=401,
                error="invalid_client",
                error_description="client_secret required",
            )
        if not verify_password(client_secret, client.client_secret_hash):
            raise OAuthError(
                status_code=401,
                error="invalid_client",
                error_description="invalid client credentials",
            )

    return client