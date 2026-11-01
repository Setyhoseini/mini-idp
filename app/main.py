"""FastAPI application factory and entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.config import get_settings
from app.db import Base, engine

from app import models  # noqa: F401  — ensures all mappers are registered


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Runs once at startup and once at shutdown."""
    # Step 2: no models yet, so create_all is a no-op.
    # Step 3+: create_all creates every table declared under app.models.
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown hooks (e.g., engine.dispose()) can go here later.


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,  # keep surface small; we only document via /docs
        lifespan=lifespan,
    )

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        # Proves the process can talk to the DB, not just that it is up.
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()