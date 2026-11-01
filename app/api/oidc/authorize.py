"""Authorization endpoint — start the Auth Code + PKCE flow."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_optional_session
from app.api.exceptions import OAuthError
from app.config import get_settings
from app.db import get_db
from app.models import User, UserSession
from app.services import client_service, oidc_service, realm_service
from app.services.authorization import compute_effective_scopes

router = APIRouter(tags=["oidc"])


def _login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(url=f"/login?return_to={quote(target, safe='')}", status_code=302)


@router.get("/authorize")
def authorize(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str = "",
    state: str | None = None,
    nonce: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str | None = None,
    db: Session = Depends(get_db),
    session: UserSession | None = Depends(get_optional_session),
) -> RedirectResponse:
    # Validate protocol shape first — before touching the session — so a bad
    # request is rejected the same way whether or not the user is logged in.
    if response_type != "code":
        raise OAuthError(
            status_code=400,
            error="unsupported_response_type",
            error_description="only response_type=code is supported",
        )
    if not code_challenge:
        raise OAuthError(
            status_code=400,
            error="invalid_request",
            error_description="PKCE code_challenge is required",
        )
    if code_challenge_method != "S256":
        raise OAuthError(
            status_code=400,
            error="invalid_request",
            error_description="only code_challenge_method=S256 is supported",
        )

    realm = realm_service.get_single_realm(db)
    try:
        client = client_service.get_client_by_public_id(
            db, realm_id=realm.id, client_id=client_id
        )
    except Exception:
        raise OAuthError(
            status_code=400, error="invalid_client", error_description="unknown client_id"
        ) from None

    if redirect_uri not in client.redirect_uris:
        raise OAuthError(
            status_code=400,
            error="invalid_request",
            error_description="redirect_uri is not registered for this client",
        )

    # Session gate: if missing or user inactive, bounce to /login.
    if session is None:
        return _login_redirect(request)
    user = db.get(User, session.user_id)
    if user is None or not user.enabled:
        return _login_redirect(request)

    requested = scope.split() if scope else []
    user_effective = compute_effective_scopes(db, user.id)
    granted = oidc_service.compute_granted_scopes(
        requested, client.allowed_scopes, user_effective
    )
    if not granted:
        raise OAuthError(
            status_code=400,
            error="invalid_scope",
            error_description="no requested scope can be granted",
        )

    settings = get_settings()
    issued = oidc_service.issue_authorization_code(
        db,
        client=client,
        user=user,
        session=session,
        redirect_uri=redirect_uri,
        scopes=granted,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        nonce=nonce,
        state=state,
        ttl_seconds=settings.authorization_code_ttl_seconds,
    )

    sep = "&" if "?" in redirect_uri else "?"
    url = f"{redirect_uri}{sep}code={quote(issued.raw_code, safe='')}"
    if state is not None:
        url += f"&state={quote(state, safe='')}"
    return RedirectResponse(url=url, status_code=302)