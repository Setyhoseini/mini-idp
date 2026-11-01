"""OAuth2-shaped HTTP exception.

Use this for anything that must surface as RFC 6749 §5.2 JSON:
    {"error": "...", "error_description": "..."}

Domain layer errors use `app.services.errors.DomainError`, not this class.
"""

from __future__ import annotations


class OAuthError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        error: str,
        error_description: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(error_description)
        self.status_code = status_code
        self.error = error
        self.error_description = error_description
        self.headers = headers or {}


def unauthorized(error: str, description: str) -> OAuthError:
    return OAuthError(
        status_code=401,
        error=error,
        error_description=description,
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(error: str, description: str) -> OAuthError:
    return OAuthError(
        status_code=403,
        error=error,
        error_description=description,
        headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
    )