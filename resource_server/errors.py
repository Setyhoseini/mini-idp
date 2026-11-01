"""Resource-server local OAuth2 error type.

The RS deliberately does NOT import app.api.exceptions — it is a separate
deployable and should not depend on IdP internals.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class RSHTTPError(Exception):
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


def unauthorized(error: str, description: str) -> RSHTTPError:
    return RSHTTPError(
        status_code=401,
        error=error,
        error_description=description,
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(error: str, description: str) -> RSHTTPError:
    return RSHTTPError(
        status_code=403,
        error=error,
        error_description=description,
        headers={"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
    )


def register_rs_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RSHTTPError)
    async def _handle(_: Request, exc: RSHTTPError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "error_description": exc.error_description},
            headers=exc.headers,
        )