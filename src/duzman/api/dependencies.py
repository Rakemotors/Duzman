"""FastAPI dependency wrappers for Duzman API routes."""

import secrets
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from duzman.db.session import get_db
from duzman.settings import Settings

API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_AUTHENTICATE_HEADER = 'ApiKey realm="duzman"'
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def get_api_db() -> Generator[Session, None, None]:
    """Yield a database session for read-only API route handlers."""
    yield from get_db()


def configured_api_key(settings: Settings) -> str:
    """Return the configured Duzman API key or raise on fail-closed startup."""
    api_key = settings.duzman_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError(
            "DUZMAN_API_KEY must be configured before serving protected API routes"
        )
    return api_key


def require_api_key(
    request: Request,
    provided_api_key: Annotated[str | None, Depends(api_key_header)],
) -> None:
    """Authorize protected read-only API requests using the X-API-Key header."""
    expected_api_key = getattr(request.app.state, "duzman_api_key", "")
    if not expected_api_key:
        raise RuntimeError(
            "DUZMAN_API_KEY must be configured before serving protected API routes"
        )
    if not provided_api_key or not secrets.compare_digest(
        provided_api_key,
        expected_api_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": API_KEY_AUTHENTICATE_HEADER},
        )
