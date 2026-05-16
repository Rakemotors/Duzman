"""FastAPI dependency wrappers for Duzman API routes."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from duzman.db.session import get_db


def get_api_db() -> Generator[Session, None, None]:
    """Yield a database session for read-only API route handlers."""
    yield from get_db()
