"""SQLAlchemy engine, declarative base, and DB session factory."""

from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

from sqlalchemy import event
from sqlalchemy.engine import Engine

# Deterministic constraint names — needed for clean migrations and clear
# error messages. Follows SQLAlchemy's recommended convention.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


_settings = get_settings()

# SQLite needs `check_same_thread=False` when the engine is shared across
# threads (FastAPI's default threadpool does this). Postgres does not.
_connect_args: dict = (
    {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(
    _settings.database_url,
    connect_args=_connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
@event.listens_for(Engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite does not enforce FKs by default. Enable per-connection."""
    if _settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()        