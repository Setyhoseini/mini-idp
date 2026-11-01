"""UserInfo endpoint — claims for the token's subject."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_bearer_claims
from app.api.exceptions import unauthorized
from app.db import get_db
from app.models import User

router = APIRouter(tags=["oidc"])


@router.get("/userinfo")
def userinfo(
    claims: dict = Depends(get_bearer_claims),
    db: Session = Depends(get_db),
) -> dict:
    sub = claims.get("sub")
    if not sub:
        raise unauthorized("invalid_token", "token has no subject")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise unauthorized("invalid_token", "subject is not a valid user id") from None

    user = db.get(User, user_id)
    if user is None or not user.enabled:
        raise unauthorized("invalid_token", "user does not exist or is disabled")

    scopes = (claims.get("scope") or "").split()
    result: dict = {"sub": sub}
    if "profile" in scopes:
        result["preferred_username"] = user.username
        name = " ".join(filter(None, [user.first_name, user.last_name]))
        if name:
            result["name"] = name
        if user.first_name:
            result["given_name"] = user.first_name
        if user.last_name:
            result["family_name"] = user.last_name
    if "email" in scopes and user.email:
        result["email"] = user.email
        result["email_verified"] = False
    return result