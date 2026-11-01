"""Introspection and revocation endpoints (RFC 7662 and RFC 7009)."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, Form, Request, Response
from sqlalchemy.orm import Session

from app.api.oidc.client_auth import resolve_client
from app.db import get_db
from app.security.jwt_signer import get_jwt_signer
from app.services import oidc_service

router = APIRouter(tags=["oidc"])


@router.post("/introspect")
def introspect(
    request: Request,
    token: str = Form(...),
    token_type_hint: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    client_secret: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    resolve_client(db, request, client_id, client_secret)
    try:
        claims = get_jwt_signer().verify(token)
    except jwt.InvalidTokenError:
        return {"active": False}
    return {
        "active": True,
        "sub": claims.get("sub"),
        "scope": claims.get("scope"),
        "client_id": claims.get("aud"),
        "iss": claims.get("iss"),
        "iat": claims.get("iat"),
        "exp": claims.get("exp"),
    }


@router.post("/revoke")
def revoke(
    request: Request,
    token: str = Form(...),
    token_type_hint: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    client_secret: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> Response:
    client = resolve_client(db, request, client_id, client_secret)
    oidc_service.revoke_refresh_token(db, raw_token=token, client=client)
    # RFC 7009 §2.2: always 200, whether or not the token existed.
    return Response(status_code=200)