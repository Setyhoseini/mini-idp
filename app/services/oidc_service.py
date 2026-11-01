"""OIDC service layer: authorization codes, token issuance, refresh, revocation."""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthorizationCode, Client, RefreshToken, User, UserSession
from app.security.jwt_signer import get_jwt_signer
from app.services.authorization import compute_effective_scopes

STANDARD_OIDC_SCOPES = frozenset({"openid", "profile", "email"})


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class IssuedCode:
    raw_code: str
    code_row: AuthorizationCode


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    id_token: str | None
    expires_in: int
    scope: str


# ---------- scope filtering ----------

def compute_granted_scopes(
    requested: list[str],
    client_allowed: list[str],
    user_effective: set[str],
) -> list[str]:
    """Filter requested scopes to those the client may ask + the user may have.

    Standard OIDC claim scopes are granted to any authenticated user; custom
    scopes require an effective grant (direct or via group).
    """
    allowed = set(client_allowed)
    granted: list[str] = []
    for name in requested:
        if name not in allowed:
            continue
        if name in STANDARD_OIDC_SCOPES or name in user_effective:
            granted.append(name)
    return granted


# ---------- authorization codes ----------

def issue_authorization_code(
    db: Session,
    *,
    client: Client,
    user: User,
    session: UserSession,
    redirect_uri: str,
    scopes: list[str],
    code_challenge: str,
    code_challenge_method: str,
    nonce: str | None,
    state: str | None,
    ttl_seconds: int,
) -> IssuedCode:
    raw = secrets.token_urlsafe(32)
    code = AuthorizationCode(
        code_hash=_hash(raw),
        client_id=client.id,
        user_id=user.id,
        session_id=session.id,
        redirect_uri=redirect_uri,
        scopes=list(scopes),
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        state=state,
        expires_at=_now() + timedelta(seconds=ttl_seconds),
    )
    db.add(code)
    db.commit()
    db.refresh(code)
    return IssuedCode(raw_code=raw, code_row=code)


def verify_pkce(code_verifier: str, stored_challenge: str) -> bool:
    """Verify PKCE S256: SHA256(verifier) base64url-no-pad == challenge."""
    digest = hashlib.sha256(code_verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return secrets.compare_digest(computed, stored_challenge)


def consume_code(
    db: Session,
    *,
    raw_code: str,
    client: Client,
    redirect_uri: str,
    code_verifier: str,
) -> AuthorizationCode:
    """Validate and consume an authorization code. Marks used_at on success."""
    code = db.execute(
        select(AuthorizationCode).where(AuthorizationCode.code_hash == _hash(raw_code))
    ).scalar_one_or_none()
    if code is None:
        raise ValueError("unknown or malformed code")
    if code.used_at is not None:
        raise ValueError("code already redeemed")
    if code.expires_at <= _now():
        raise ValueError("code expired")
    if code.client_id != client.id:
        raise ValueError("code was issued to a different client")
    if code.redirect_uri != redirect_uri:
        raise ValueError("redirect_uri does not match the one used at /authorize")
    if not verify_pkce(code_verifier, code.code_challenge):
        raise ValueError("PKCE verification failed")

    session = db.get(UserSession, code.session_id)
    if session is None or session.revoked_at is not None or session.expires_at <= _now():
        raise ValueError("issuing session is no longer active")

    code.used_at = _now()
    db.commit()
    db.refresh(code)
    return code


# ---------- token issuance ----------

def _access_claims(user: User, client: Client, scopes: list[str]) -> dict:
    return {
        "sub": str(user.id),
        "aud": client.client_id,
        "scope": " ".join(scopes),
        "typ": "at+jwt",
        "jti": secrets.token_urlsafe(16),
    }


def _id_claims(user: User, client: Client, scopes: list[str], nonce: str | None, auth_time: int) -> dict:
    claims: dict = {
        "sub": str(user.id),
        "aud": client.client_id,
        "auth_time": auth_time,
        "preferred_username": user.username,
    }
    if nonce is not None:
        claims["nonce"] = nonce
    if "profile" in scopes:
        name = " ".join(filter(None, [user.first_name, user.last_name]))
        if name:
            claims["name"] = name
        if user.first_name:
            claims["given_name"] = user.first_name
        if user.last_name:
            claims["family_name"] = user.last_name
    if "email" in scopes and user.email:
        claims["email"] = user.email
        claims["email_verified"] = False
    return claims


def _mint_bundle(
    db: Session,
    *,
    client: Client,
    user: User,
    session_id: int,
    scopes: list[str],
    nonce: str | None,
    auth_time: int,
    rotated_from: int | None = None,
) -> TokenBundle:
    settings = get_settings()
    signer = get_jwt_signer()

    access_token = signer.sign(
        _access_claims(user, client, scopes),
        ttl_seconds=settings.access_token_ttl_seconds,
    )

    id_token: str | None = None
    if "openid" in scopes:
        id_token = signer.sign(
            _id_claims(user, client, scopes, nonce, auth_time),
            ttl_seconds=settings.id_token_ttl_seconds,
        )

    raw_refresh = secrets.token_urlsafe(32)
    refresh = RefreshToken(
        token_hash=_hash(raw_refresh),
        client_id=client.id,
        user_id=user.id,
        session_id=session_id,
        scopes=list(scopes),
        expires_at=_now() + timedelta(seconds=settings.refresh_token_ttl_seconds),
        rotated_from=rotated_from,
    )
    db.add(refresh)
    db.commit()
    db.refresh(refresh)

    return TokenBundle(
        access_token=access_token,
        refresh_token=raw_refresh,
        id_token=id_token,
        expires_in=settings.access_token_ttl_seconds,
        scope=" ".join(scopes),
    )


def issue_tokens_for_code(
    db: Session,
    *,
    code: AuthorizationCode,
    client: Client,
    user: User,
) -> TokenBundle:
    return _mint_bundle(
        db,
        client=client,
        user=user,
        session_id=code.session_id,
        scopes=list(code.scopes),
        nonce=code.nonce,
        auth_time=int(code.created_at.timestamp()),
    )


def refresh_tokens(
    db: Session,
    *,
    raw_refresh_token: str,
    client: Client,
) -> TokenBundle:
    """Rotate a refresh token. Recomputes scopes from current effective set."""
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_refresh_token))
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        raise ValueError("invalid or already-revoked refresh token")
    if row.expires_at <= _now():
        raise ValueError("refresh token expired")
    if row.client_id != client.id:
        raise ValueError("refresh token was issued to a different client")

    session = db.get(UserSession, row.session_id)
    if session is None or session.revoked_at is not None or session.expires_at <= _now():
        raise ValueError("session is no longer active")

    user = db.get(User, row.user_id)
    if user is None or not user.enabled:
        raise ValueError("user is not active")

    # Scope re-evaluation: intersection of stored, allowed, and current-effective.
    current_effective = compute_effective_scopes(db, user.id)
    client_allowed = set(client.allowed_scopes)
    new_scopes: list[str] = []
    for name in row.scopes:
        if name not in client_allowed:
            continue
        if name in STANDARD_OIDC_SCOPES or name in current_effective:
            new_scopes.append(name)

    if not new_scopes:
        raise ValueError("no scopes remain after re-evaluation")

    row.revoked_at = _now()

    return _mint_bundle(
        db,
        client=client,
        user=user,
        session_id=row.session_id,
        scopes=new_scopes,
        nonce=None,
        auth_time=int(row.created_at.timestamp()),
        rotated_from=row.id,
    )


def revoke_refresh_token(db: Session, *, raw_token: str, client: Client) -> None:
    """Revoke a refresh token. Idempotent and silently no-ops for foreign/missing."""
    row = db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token))
    ).scalar_one_or_none()
    if row is None:
        return
    if row.client_id != client.id:
        return
    if row.revoked_at is None:
        row.revoked_at = _now()
        db.commit()