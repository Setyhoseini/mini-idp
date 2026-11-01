"""FastAPI dependencies: bearer-token verification and scope enforcement."""

from __future__ import annotations

from typing import Callable

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.services import session_service

from app.api.exceptions import forbidden, unauthorized
from app.db import get_db
from app.models import User, UserSession
from app.security.jwt_signer import get_jwt_signer


def get_bearer_claims(authorization: str | None = Header(default=None)) -> dict:
    """Extract and verify the Bearer JWT. Returns its claims dict.

    Does NOT check scope or user state — those are the caller's job
    (`require_scope` composes those on top).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized("invalid_request", "missing or malformed Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    try:
        return get_jwt_signer().verify(token)
    except jwt.ExpiredSignatureError:
        raise unauthorized("invalid_token", "token has expired") from None
    except jwt.InvalidTokenError as exc:
        raise unauthorized("invalid_token", f"token rejected: {exc}") from None


def require_scope(required: str) -> Callable[[dict, Session], dict]:
    """Build a dependency that enforces `required` in the token's scope claim."""

    def _checker(
        claims: dict = Depends(get_bearer_claims),
        db: Session = Depends(get_db),
    ) -> dict:
        token_scopes = (claims.get("scope") or "").split()
        if required not in token_scopes:
            raise forbidden("insufficient_scope", f"requires scope '{required}'")

        sub = claims.get("sub")
        if sub is None:
            raise unauthorized("invalid_token", "token has no subject")
        try:
            user_id = int(sub)
        except (TypeError, ValueError):
            raise unauthorized("invalid_token", "subject is not a valid user id") from None

        user = db.get(User, user_id)
        if user is None or not user.enabled:
            raise unauthorized("invalid_token", "user does not exist or is disabled")
        return claims

    return _checker

def get_optional_session(
    request: Request,
    db: Session = Depends(get_db),
) -> UserSession | None:
    """Return the active session for this request, or None.

    Reads the cookie name from settings so there's a single source of truth
    for the cookie name across login, logout, and this dependency.
    """
    from app.config import get_settings

    cookie_name = get_settings().session_cookie_name
    raw_token = request.cookies.get(cookie_name)
    if not raw_token:
        return None
    return session_service.get_active_session_by_token(db, raw_token)


# Ready-made dependency for the admin surface.
get_current_admin = require_scope("admin")