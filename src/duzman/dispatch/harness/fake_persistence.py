# src/duzman/dispatch/harness/fake_persistence.py
# Dispatch harness fake persistence. Owns an in-memory SQLite engine seeded for
# deterministic repository-backed dispatch delivery tests.
"""In-memory async SQLite persistence for the dispatch harness."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from duzman.dispatch.persistence.repository import DispatchDeliveryRepository


class FakePersistence:
    """Async context manager for repository-backed in-memory persistence."""

    def __init__(self) -> None:
        """Initialize an unopened fake persistence context."""
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def __aenter__(self) -> FakePersistence:
        """Create the in-memory schema, seed rows, and return this context."""
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as connection:
            await connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            await _create_schema(connection)
            await _seed_rows(connection)

        self._engine = engine
        self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Dispose the in-memory engine on context exit."""
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._session_factory = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield one async session bound to the fake persistence engine."""
        if self._session_factory is None:
            raise RuntimeError("FakePersistence must be entered before use")
        async with self._session_factory() as db_session:
            yield db_session

    def repository(self, session: AsyncSession) -> DispatchDeliveryRepository:
        """Build a real dispatch delivery repository for a fake session."""
        return DispatchDeliveryRepository(session)


async def _create_schema(connection: Any) -> None:
    """Create the minimal tables required by dispatch persistence."""
    await connection.exec_driver_sql(
        """
        CREATE TABLE assets (
            symbol VARCHAR(10) PRIMARY KEY,
            name VARCHAR(50),
            enabled BOOLEAN DEFAULT 1,
            added_at DATETIME
        )
        """
    )
    await connection.exec_driver_sql(
        """
        CREATE TABLE pattern_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL,
            pattern_name VARCHAR(50) NOT NULL,
            asset VARCHAR(10) NOT NULL,
            severity VARCHAR(10) NOT NULL,
            conditions_snapshot JSON,
            ai_explanation TEXT,
            alert_sent BOOLEAN,
            user_feedback VARCHAR(20),
            user_feedback_at DATETIME,
            FOREIGN KEY(asset) REFERENCES assets(symbol)
        )
        """
    )
    await connection.exec_driver_sql(
        """
        CREATE TABLE alert_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            channel VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            sent_at DATETIME,
            telegram_message_id BIGINT,
            ack_at DATETIME,
            snooze_until DATETIME,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            UNIQUE(alert_id, channel),
            FOREIGN KEY(alert_id) REFERENCES pattern_triggers(id) ON DELETE CASCADE
        )
        """
    )


async def _seed_rows(connection: Any) -> None:
    """Seed BTC plus three pattern triggers for deterministic harness runs."""
    await connection.exec_driver_sql(
        "INSERT INTO assets (symbol, name, enabled, added_at) VALUES ('BTC', 'Bitcoin', 1, ?)",
        (datetime(2026, 6, 1, 0, 0, tzinfo=UTC),),
    )
    for trigger_id in (1, 2, 3):
        await connection.exec_driver_sql(
            """
            INSERT INTO pattern_triggers
                (id, ts, pattern_name, asset, severity, conditions_snapshot, alert_sent)
            VALUES (?, ?, 'test_pattern', 'BTC', 'WARNING', '{"gate_decision": "ALLOW"}', 0)
            """,
            (trigger_id, datetime(2026, 6, 1, 12, trigger_id, tzinfo=UTC)),
        )
