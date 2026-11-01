"""Shared cookie helpers for the auth surface (JSON and HTML routers)."""

from __future__ import annotations

from fastapi import Response

from app.config import get_settings


def attach_session_cookie(response: Response, raw_token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.session_cookie_name,
        value=raw_token,
        max_age=s.session_ttl_seconds,
        httponly=True,
        secure=s.session_cookie_secure,
        samesite=s.session_cookie_samesite,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(
        key=s.session_cookie_name,
        path="/",
        secure=s.session_cookie_secure,
        httponly=True,
        samesite=s.session_cookie_samesite,
    )