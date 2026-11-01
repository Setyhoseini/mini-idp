"""Demo resource server — validates Bearer tokens from the IdP and enforces scopes."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from resource_server.deps import require_scope
from resource_server.errors import register_rs_error_handlers
from resource_server.settings import get_rs_settings


def create_app() -> FastAPI:
    settings = get_rs_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", redoc_url=None)
    register_rs_error_handlers(app)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/api/orders", tags=["protected"])
    def list_orders(claims: dict = Depends(require_scope("orders.read"))) -> dict:
        return {
            "sub": claims["sub"],
            "orders": [
                {"id": 1, "item": "Widget", "status": "shipped"},
                {"id": 2, "item": "Gadget", "status": "pending"},
            ],
        }

    @app.post("/api/orders", tags=["protected"])
    def create_order(claims: dict = Depends(require_scope("orders.write"))) -> dict:
        return {"created": True, "sub": claims["sub"]}

    @app.get("/api/reports", tags=["protected"])
    def list_reports(claims: dict = Depends(require_scope("reports.read"))) -> dict:
        return {"sub": claims["sub"], "reports": [{"month": "2025-11", "total": 42}]}

    return app


app = create_app()