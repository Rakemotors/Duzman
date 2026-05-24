from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from duzman.settings import settings


class Base(DeclarativeBase):
    """Base class for Duzman SQLAlchemy ORM models."""

    pass


_engine: Engine | None = None
SessionLocal = sessionmaker(autocommit=False, autoflush=False)


def get_engine() -> Engine:
    """Return the configured SQLAlchemy engine without creating it at import time."""
    global _engine
    if _engine is None:
        database_url = settings.database_url.get_secret_value()
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL must be configured before opening database sessions."
            )
        _engine = create_engine(database_url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    """Return the project session factory bound to the configured engine."""
    if SessionLocal.kw.get("bind") is None:
        SessionLocal.configure(bind=get_engine())
    return SessionLocal


def get_db():
    """Yield a database session for FastAPI dependencies and scripts."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
