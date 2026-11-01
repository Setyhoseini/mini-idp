"""Token endpoint — code exchange and refresh rotation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.api.exceptions import OAuthError
from app.api.oidc.client_auth import resolve_client
from app.db import get_db
from app.models import User
from app.services import oidc_service

router = APIRouter(tags=["oidc"])


@router.post("/token")
def token(
    request: Request,
    grant_type: str = Form(...),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
    code_verifier: str | None = Form(default=None),
    refresh_token: str | None = Form(default=None),
    client_id: str | None = Form(default=None),
    client_secret: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    client = resolve_client(db, request, client_id, client_secret)

    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            raise OAuthError(
                status_code=400,
                error="invalid_request",
                error_description="code, redirect_uri, and code_verifier are required",
            )
        try:
            code_row = oidc_service.consume_code(
                db,
                raw_code=code,
                client=client,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        except ValueError as exc:
            raise OAuthError(
                status_code=400, error="invalid_grant", error_description=str(exc)
            ) from None

        user = db.get(User, code_row.user_id)
        if user is None or not user.enabled:
            raise OAuthError(
                status_code=400,
                error="invalid_grant",
                error_description="user no longer active",
            )
        bundle = oidc_service.issue_tokens_for_code(
            db, code=code_row, client=client, user=user
        )
        return _bundle_to_dict(bundle)

    if grant_type == "refresh_token":
        if not refresh_token:
            raise OAuthError(
                status_code=400,
                error="invalid_request",
                error_description="refresh_token is required",
            )
        try:
            bundle = oidc_service.refresh_tokens(
                db, raw_refresh_token=refresh_token, client=client
            )
        except ValueError as exc:
            raise OAuthError(
                status_code=400, error="invalid_grant", error_description=str(exc)
            ) from None
        return _bundle_to_dict(bundle)

    raise OAuthError(
        status_code=400,
        error="unsupported_grant_type",
        error_description=f"grant_type {grant_type!r} is not supported",
    )


def _bundle_to_dict(bundle: oidc_service.TokenBundle) -> dict:
    result = {
        "access_token": bundle.access_token,
        "token_type": "Bearer",
        "expires_in": bundle.expires_in,
        "refresh_token": bundle.refresh_token,
        "scope": bundle.scope,
    }
    if bundle.id_token is not None:
        result["id_token"] = bundle.id_token
    return result