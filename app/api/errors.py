"""Error handlers that translate domain and OAuth errors to JSON responses."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.exceptions import OAuthError
from app.services.errors import DomainError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _handle_domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.code, "error_description": exc.message},
        )

    @app.exception_handler(OAuthError)
    async def _handle_oauth(_: Request, exc: OAuthError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error, "error_description": exc.error_description},
            headers=exc.headers,
        )