"""
database.py — SQLAlchemy engine, session factory, and Base.

Uses synchronous SQLAlchemy 2.0 style with SQLite for local development.
Provides a ``get_db`` dependency for FastAPI route injection.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# ---------------------------------------------------------------------------
# Engine — connect_args needed for SQLite thread safety with FastAPI
# ---------------------------------------------------------------------------
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Table initialisation helper
# ---------------------------------------------------------------------------
def init_db() -> None:
    """Create all tables that don't yet exist."""
    Base.metadata.create_all(bind=engine)


# ---------------------------------------------------------------------------
# FastAPI dependency — yields a session per request
# ---------------------------------------------------------------------------
def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it's closed after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
