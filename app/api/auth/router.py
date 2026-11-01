"""JSON authentication endpoints: /auth/login, /auth/logout, /auth/session."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.auth.cookies import attach_session_cookie, clear_session_cookie
from app.api.auth.schemas import LoginRequest, LoginResponse, SessionInfoResponse, SessionUser
from app.api.deps import get_optional_session
from app.api.exceptions import OAuthError
from app.config import get_settings
from app.db import get_db
from app.models import UserSession
from app.services import rate_limiter, session_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    settings = get_settings()
    if not rate_limiter.check(
        f"login:{_client_ip(request)}",
        limit=settings.login_rate_limit_per_minute,
    ):
        raise OAuthError(
            status_code=429,
            error="rate_limited",
            error_description="too many login attempts; try again shortly",
            headers={"Retry-After": "60"},
        )

    result = session_service.attempt_login(
        db,
        username=payload.username,
        password=payload.password,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
        ttl_seconds=settings.session_ttl_seconds,
    )
    if result is None:
        raise OAuthError(
            status_code=401,
            error="invalid_credentials",
            error_description="invalid username or password",
        )

    body = LoginResponse(
        user=SessionUser(id=result.user.id, username=result.user.username, email=result.user.email),
        session_exp=int(result.session.expires_at.timestamp()),
    )
    response = Response(
        content=body.model_dump_json(),
        media_type="application/json",
        status_code=200,
    )
    attach_session_cookie(response, result.raw_token)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: Session = Depends(get_db),
    session: UserSession | None = Depends(get_optional_session),
) -> Response:
    if session is not None:
        session_service.revoke_session(db, session.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/session", response_model=SessionInfoResponse)
def session_info(session: UserSession | None = Depends(get_optional_session)) -> SessionInfoResponse:
    if session is None:
        return SessionInfoResponse(authenticated=False)
    return SessionInfoResponse(
        authenticated=True,
        user=SessionUser(
            id=session.user.id,
            username=session.user.username,
            email=session.user.email,
        ),
        session_exp=int(session.expires_at.timestamp()),
    )