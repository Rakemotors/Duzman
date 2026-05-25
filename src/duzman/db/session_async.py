# src/duzman/db/session_async.py
# Async SQLAlchemy session wiring shared by runtime components.
# Owns URL conversion only; callers own engine disposal lifecycle.
"""Build async SQLAlchemy engines and session factories from settings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from duzman.settings import Settings


@dataclass(frozen=True)
class AsyncDatabaseSessionComponents:
    """Async database engine and session factory for runtime composition roots."""

    async_engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def build_async_database_session_components(
    settings: Settings,
) -> AsyncDatabaseSessionComponents:
    """Build an async SQLAlchemy engine and session factory from settings.

    Parameters:
        settings: Runtime settings containing the sync `DATABASE_URL`.

    Returns:
        Async engine and `async_sessionmaker` configured for PostgreSQL asyncpg.

    Raises:
        ValueError: If `DATABASE_URL` is empty or has an unsupported scheme.
    """
    async_url = build_async_database_url(settings.database_url.get_secret_value())
    async_engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
    return AsyncDatabaseSessionComponents(
        async_engine=async_engine,
        session_factory=async_sessionmaker(async_engine, expire_on_commit=False),
    )


def build_async_database_url(sync_url: str) -> str:
    """Return an asyncpg SQLAlchemy URL derived from a supported sync URL.

    Parameters:
        sync_url: Sync SQLAlchemy PostgreSQL URL from runtime settings.

    Returns:
        SQLAlchemy asyncpg URL.

    Raises:
        ValueError: If the URL is empty or uses an unsupported scheme.
    """
    if not sync_url:
        raise ValueError("DATABASE_URL must be configured for async database sessions")
    if sync_url.startswith("postgresql+asyncpg://"):
        return sync_url
    if sync_url.startswith("postgresql://"):
        return f"postgresql+asyncpg://{sync_url.removeprefix('postgresql://')}"
    if sync_url.startswith("postgres://"):
        return f"postgresql+asyncpg://{sync_url.removeprefix('postgres://')}"
    raise ValueError("DATABASE_URL scheme is not supported for async database sessions")
