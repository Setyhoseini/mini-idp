"""SQLAlchemy engine, declarative base, and DB session factory."""

from collections.abc import Generator

from sqlalchemy import DateTime, MetaData, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

from sqlalchemy import event
from sqlalchemy.engine import Engine

from datetime import datetime, timezone

class UTCDateTime(TypeDecorator):
    """A DateTime column that stores UTC and always returns aware UTC datetimes.

    SQLite (and some other dialects) do not preserve timezone offsets: values
    are written as naive strings and read back as naive datetimes. Without
    this type, comparing `row.expires_at <= datetime.now(timezone.utc)` raises
    `TypeError: can't compare offset-naive and offset-aware datetimes`.

    This type normalizes on both sides:
      - bind:   aware -> naive UTC (stored as TEXT)
      - result: naive -> aware UTC (returned to application code)

    Application code then always works with timezone-aware datetimes and never
    needs to know which dialect produced the value.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # Discipline check: naive values are assumed to already be UTC.
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

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