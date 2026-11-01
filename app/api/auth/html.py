"""HTML login endpoints — the browser's entry point for Auth Code flow."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.auth.cookies import attach_session_cookie
from app.api.exceptions import OAuthError
from app.config import get_settings
from app.db import get_db
from app.services import rate_limiter, session_service

router = APIRouter(tags=["auth-html"])
_templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent.parent / "templates"))


def _safe_return_to(value: str | None) -> str:
    """Allow only relative paths. Reject absolute and protocol-relative URLs."""
    if not value:
        return "/"
    if not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, return_to: str | None = None) -> HTMLResponse:
    return _templates.TemplateResponse(
        request, "login.html", {"return_to": return_to or "", "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    return_to: str = Form(""),
    db: Session = Depends(get_db),
):
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
        username=username,
        password=password,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
        ttl_seconds=settings.session_ttl_seconds,
    )
    if result is None:
        return _templates.TemplateResponse(
            request,
            "login.html",
            {"return_to": return_to, "error": "Invalid username or password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    redirect_to = _safe_return_to(return_to)
    response = RedirectResponse(url=redirect_to, status_code=status.HTTP_303_SEE_OTHER)
    attach_session_cookie(response, result.raw_token)
    return response