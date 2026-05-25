"""Database connection management for PostgreSQL (local or Cloud SQL)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import MetaData, text
from sqlmodel import Session, SQLModel, create_engine

from core.config import get_settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Generator

convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)
SQLModel.metadata.naming_convention = convention

_engine = None


def _normalize_url(url: str) -> str:
    """Normalize database URL for SQLAlchemy compatibility."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _create_cloud_sql_engine(settings):  # noqa: ANN001, ANN202
    """Create an engine using the Cloud SQL Python Connector for IAM auth."""
    from google.cloud.sql.connector import Connector

    connector = Connector()

    def getconn():  # noqa: ANN202
        return connector.connect(
            settings.cloud_sql_instance,
            "pg8000",
            user="app",
            db="precision_genomics",
            enable_iam_auth=True,
        )

    return create_engine(
        "postgresql+pg8000://",
        creator=getconn,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


def get_engine():
    """Get SQLAlchemy engine with connection pooling (lazy singleton)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.cloud_sql_instance:
            _engine = _create_cloud_sql_engine(settings)
        else:
            database_url = _normalize_url(settings.database_url)
            _engine = create_engine(
                database_url,
                echo=settings.debug,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
    return _engine


def reset_engine() -> None:
    """Reset the engine singleton (for testing or shutdown)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session() -> Generator[Session, None, None]:
    """Yield a SQLModel session for FastAPI dependency injection."""
    with Session(get_engine()) as session:
        yield session


def init_composite_index(table_name: str) -> None:
    """Create a composite index for time-series-like queries.

    Replaces the previous TimescaleDB hypertable approach with a standard
    PostgreSQL composite index compatible with Cloud SQL.
    """
    engine = get_engine()
    index_name = f"ix_{table_name}_panel_feature_ts"
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = :table_name)"),
                {"table_name": table_name},
            )
            if not result.scalar():
                return

            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {index_name} "  # noqa: S608
                    f"ON {table_name} (panel_id, feature_name, ts DESC)"
                )
            )
            conn.commit()
    except Exception:
        logger.warning("Failed to ensure index %s on %s", index_name, table_name, exc_info=True)
