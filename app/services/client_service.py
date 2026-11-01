"""OIDC client registration and management."""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Client
from app.security.passwords import hash_password
from app.services.audit import record
from app.services.errors import ClientNotFound, DuplicateClientId

_SECRET_BYTES = 32


def register_client(
    db: Session,
    *,
    realm_id: int,
    client_id: str,
    client_name: str,
    redirect_uris: list[str],
    allowed_scopes: list[str],
    is_public: bool,
    post_logout_redirect_uris: list[str] | None = None,
) -> tuple[Client, str | None]:
    """Register a client. Returns (client, plaintext_secret).

    For public clients (PKCE-only) the secret is None — never set.
    For confidential clients the returned secret is the *only* time the
    plaintext exists; only its hash is persisted.
    """
    client_id = client_id.strip()
    if not client_id:
        raise ValueError("client_id must be non-empty")
    if not redirect_uris:
        raise ValueError("redirect_uris must contain at least one URI")

    existing = db.execute(
        select(Client).where(Client.realm_id == realm_id, Client.client_id == client_id)
    ).scalar_one_or_none()
    if existing is not None:
        raise DuplicateClientId(client_id)

    plaintext_secret: str | None = None
    secret_hash: str | None = None
    if not is_public:
        plaintext_secret = secrets.token_urlsafe(_SECRET_BYTES)
        secret_hash = hash_password(plaintext_secret)

    client = Client(
        realm_id=realm_id,
        client_id=client_id,
        client_name=client_name,
        client_secret_hash=secret_hash,
        redirect_uris=list(redirect_uris),
        post_logout_redirect_uris=list(post_logout_redirect_uris or []),
        allowed_scopes=list(allowed_scopes),
        is_public=is_public,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    record("client.registered", client_pk=client.id, client_id=client.client_id, is_public=is_public)
    return client, plaintext_secret


def get_client_by_public_id(db: Session, *, realm_id: int, client_id: str) -> Client:
    client = db.execute(
        select(Client).where(Client.realm_id == realm_id, Client.client_id == client_id)
    ).scalar_one_or_none()
    if client is None:
        raise ClientNotFound(client_id)
    return client


def list_clients(db: Session, *, realm_id: int) -> list[Client]:
    return list(
        db.execute(
            select(Client).where(Client.realm_id == realm_id).order_by(Client.client_id)
        ).scalars()
    )


def update_client(
    db: Session,
    *,
    realm_id: int,
    client_id: str,
    client_name: str | None = None,
    redirect_uris: list[str] | None = None,
    post_logout_redirect_uris: list[str] | None = None,
    allowed_scopes: list[str] | None = None,
) -> Client:
    client = get_client_by_public_id(db, realm_id=realm_id, client_id=client_id)
    if client_name is not None:
        client.client_name = client_name
    if redirect_uris is not None:
        client.redirect_uris = list(redirect_uris)
    if post_logout_redirect_uris is not None:
        client.post_logout_redirect_uris = list(post_logout_redirect_uris)
    if allowed_scopes is not None:
        client.allowed_scopes = list(allowed_scopes)
    db.commit()
    db.refresh(client)
    record("client.updated", client_pk=client.id, client_id=client.client_id)
    return client


def delete_client(db: Session, *, realm_id: int, client_id: str) -> None:
    client = get_client_by_public_id(db, realm_id=realm_id, client_id=client_id)
    db.delete(client)
    db.commit()
    record("client.deleted", client_id=client_id)