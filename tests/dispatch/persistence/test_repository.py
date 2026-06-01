# tests/dispatch/persistence/test_repository.py
# Dispatch delivery repository tests. Verifies idempotent SQLite persistence
# for the existing alert_deliveries ORM model.
"""Tests for DispatchDeliveryRepository."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from duzman.db.models import AlertDelivery
from duzman.dispatch.persistence.repository import DispatchDeliveryRepository
from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_SENT,
    TELEGRAM_CHANNEL,
    AlertDeliveryRow,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_record_delivery_inserts_one_row(session: AsyncSession) -> None:
    """Recording a new delivery should insert one row."""
    result = await DispatchDeliveryRepository(session).record_delivery(_sent_row())

    assert result.persisted is True
    assert result.row_id is not None and result.row_id > 0
    assert result.existing_row_id is None


@pytest.mark.asyncio
async def test_record_delivery_duplicate_returns_existing_row_id(
    session: AsyncSession,
) -> None:
    """Duplicate trigger/channel writes should be idempotent."""
    repository = DispatchDeliveryRepository(session)

    first = await repository.record_delivery(_sent_row())
    second = await repository.record_delivery(_sent_row())

    assert first.persisted is True
    assert second.persisted is False
    assert second.existing_row_id == first.row_id


@pytest.mark.asyncio
async def test_record_delivery_allows_different_channels_same_trigger(
    session: AsyncSession,
) -> None:
    """The idempotency boundary should include channel."""
    repository = DispatchDeliveryRepository(session)

    telegram = await repository.record_delivery(_sent_row(channel=TELEGRAM_CHANNEL))
    audit = await repository.record_delivery(
        AlertDeliveryRow(
            pattern_trigger_id=1,
            channel="audit",
            status=DELIVERY_STATUS_SENT,
            telegram_message_id=None,
            error_message=None,
            sent_at=NOW,
        )
    )

    assert telegram.persisted is True
    assert audit.persisted is True


@pytest.mark.asyncio
async def test_record_delivery_allows_different_triggers_same_channel(
    session: AsyncSession,
) -> None:
    """Different pattern triggers should each get a delivery row."""
    repository = DispatchDeliveryRepository(session)

    first = await repository.record_delivery(_sent_row(pattern_trigger_id=1))
    second = await repository.record_delivery(_sent_row(pattern_trigger_id=2))

    assert first.persisted is True
    assert second.persisted is True


@pytest.mark.asyncio
async def test_find_existing_returns_row(session: AsyncSession) -> None:
    """find_existing should map an ORM row back to the dispatch row contract."""
    repository = DispatchDeliveryRepository(session)
    await repository.record_delivery(_sent_row())

    row = await repository.find_existing(
        pattern_trigger_id=1,
        channel=TELEGRAM_CHANNEL,
    )

    assert row is not None
    assert row.pattern_trigger_id == 1
    assert row.status == DELIVERY_STATUS_SENT
    assert row.telegram_message_id == 123


@pytest.mark.asyncio
async def test_find_existing_returns_none_when_absent(session: AsyncSession) -> None:
    """find_existing should return None for missing trigger/channel pairs."""
    row = await DispatchDeliveryRepository(session).find_existing(
        pattern_trigger_id=1,
        channel=TELEGRAM_CHANNEL,
    )

    assert row is None


@pytest.mark.asyncio
async def test_mark_acknowledged_updates_row(session: AsyncSession) -> None:
    """mark_acknowledged should set ack_at and updated_at."""
    repository = DispatchDeliveryRepository(session)
    result = await repository.record_delivery(_sent_row())
    assert result.row_id is not None
    ack_at = datetime(2026, 6, 1, 13, 0, tzinfo=UTC)

    await repository.mark_acknowledged(row_id=result.row_id, ack_at=ack_at)

    delivery = await session.get(AlertDelivery, result.row_id)
    assert delivery is not None
    assert delivery.ack_at is not None
    assert delivery.ack_at.replace(tzinfo=UTC) == ack_at
    assert delivery.updated_at.replace(tzinfo=UTC) == ack_at


@pytest.mark.asyncio
async def test_mark_acknowledged_missing_row_raises(session: AsyncSession) -> None:
    """mark_acknowledged should fail clearly for missing rows."""
    with pytest.raises(ValueError, match="alert delivery row was not found"):
        await DispatchDeliveryRepository(session).mark_acknowledged(
            row_id=999,
            ack_at=NOW,
        )


@pytest.mark.asyncio
async def test_concurrent_insert_race_records_one_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Concurrent inserts should produce one insert and one idempotent conflict."""

    async def record_once() -> bool:
        async with session_factory() as session:
            async with session.begin():
                result = await DispatchDeliveryRepository(session).record_delivery(_sent_row())
                return result.persisted

    persisted_values = await asyncio.gather(record_once(), record_once())

    async with session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(AlertDelivery))

    assert sorted(persisted_values) == [False, True]
    assert count == 1


@pytest.mark.asyncio
async def test_unknown_dialect_raises_not_implemented(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unsupported SQL dialects should fail explicitly."""
    repository = DispatchDeliveryRepository(session)
    monkeypatch.setattr(repository, "_dialect_name", lambda: "mysql")

    with pytest.raises(NotImplementedError, match="unsupported alert delivery dialect"):
        await repository.record_delivery(_sent_row())


def _sent_row(
    *,
    pattern_trigger_id: int = 1,
    channel: str = TELEGRAM_CHANNEL,
) -> AlertDeliveryRow:
    """Build a valid sent delivery row."""
    return AlertDeliveryRow(
        pattern_trigger_id=pattern_trigger_id,
        channel=channel,
        status=DELIVERY_STATUS_SENT,
        telegram_message_id=123 if channel == TELEGRAM_CHANNEL else None,
        error_message=None,
        sent_at=NOW,
    )
