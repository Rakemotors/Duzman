# tests/dispatch/persistence/conftest.py
# Dispatch persistence fixtures. Creates an in-memory async SQLite schema for
# alert_deliveries repository tests without external database configuration.
"""Fixtures for dispatch persistence tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    """Create an in-memory async SQLite engine with minimal dispatch schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        await _create_schema(connection)
        await _seed_rows(connection)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the in-memory test engine."""
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Yield one async SQLite session."""
    async with session_factory() as db_session:
        yield db_session


async def _create_schema(connection: Any) -> None:
    """Create minimal tables needed by dispatch persistence tests."""
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
    """Seed one asset and two pattern triggers for delivery tests."""
    await connection.exec_driver_sql(
        "INSERT INTO assets (symbol, name, enabled, added_at) VALUES ('BTC', 'Bitcoin', 1, ?)",
        (datetime(2026, 6, 1, 0, 0, tzinfo=UTC),),
    )
    for trigger_id in (1, 2):
        await connection.exec_driver_sql(
            """
            INSERT INTO pattern_triggers
                (id, ts, pattern_name, asset, severity, conditions_snapshot, alert_sent)
            VALUES (?, ?, 'test_pattern', 'BTC', 'WARNING', '{"gate_decision": "ALLOW"}', 0)
            """,
            (trigger_id, datetime(2026, 6, 1, 12, trigger_id, tzinfo=UTC)),
        )
