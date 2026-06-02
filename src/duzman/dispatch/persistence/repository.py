# src/duzman/dispatch/persistence/repository.py
# Dispatch delivery repository. Persists Telegram delivery outcomes into the
# existing alert_deliveries ORM table without owning session or engine lifecycle.
"""Session-scoped dispatch delivery persistence repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import AlertDelivery
from duzman.dispatch.persistence.row import AlertDeliveryRow, RecordDeliveryResult

DispatchDeliveryDialect = Literal["postgresql", "sqlite"]
DISPATCH_DELIVERY_DIALECT_POSTGRESQL: DispatchDeliveryDialect = "postgresql"
DISPATCH_DELIVERY_DIALECT_SQLITE: DispatchDeliveryDialect = "sqlite"
SUPPORTED_DISPATCH_DELIVERY_DIALECTS = frozenset(
    [
        DISPATCH_DELIVERY_DIALECT_POSTGRESQL,
        DISPATCH_DELIVERY_DIALECT_SQLITE,
    ]
)


class DispatchDeliveryRepository:
    """Persist dispatch delivery outcomes using an injected async session."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        dialect: DispatchDeliveryDialect,
    ) -> None:
        """Initialize a repository scoped to one caller-owned session.

        Parameters:
            session: Caller-owned async SQLAlchemy session.
            dialect: Explicit SQL dialect used to build the idempotent insert.

        Raises:
            NotImplementedError: If `dialect` is outside the supported set.
        """
        if dialect not in SUPPORTED_DISPATCH_DELIVERY_DIALECTS:
            raise NotImplementedError(f"unsupported alert delivery dialect: {dialect}")
        self._session = session
        self._dialect = dialect

    async def record_delivery(self, row: AlertDeliveryRow) -> RecordDeliveryResult:
        """Idempotently insert one alert_deliveries row.

        Caller owns transaction commit/rollback, session lifecycle, and engine
        disposal. This method maps `row.pattern_trigger_id` to DB column
        `alert_deliveries.alert_id`.

        Raises:
            NotImplementedError: If the configured dialect is not PostgreSQL or SQLite.
        """
        statement = self._insert_statement(row)
        inserted_id = await self._session.scalar(statement)
        if inserted_id is not None:
            return RecordDeliveryResult(
                persisted=True,
                row_id=int(inserted_id),
                existing_row_id=None,
            )

        existing_id = await self._existing_row_id(
            pattern_trigger_id=row.pattern_trigger_id,
            channel=row.channel,
        )
        if existing_id is None:
            raise RuntimeError("delivery insert conflicted but existing row was not found")
        return RecordDeliveryResult(
            persisted=False,
            row_id=None,
            existing_row_id=existing_id,
        )

    async def find_existing(
        self,
        *,
        pattern_trigger_id: int,
        channel: str,
    ) -> AlertDeliveryRow | None:
        """Return an existing delivery row by pattern trigger id and channel."""
        row = await self._session.scalar(
            select(AlertDelivery).where(
                AlertDelivery.alert_id == pattern_trigger_id,
                AlertDelivery.channel == channel,
            )
        )
        if row is None:
            return None
        return _row_from_orm(row)

    async def mark_acknowledged(self, *, row_id: int, ack_at: datetime) -> None:
        """Mark one delivery row acknowledged.

        Raises:
            ValueError: If `ack_at` is naive or the row does not exist.
        """
        if ack_at.tzinfo is None or ack_at.utcoffset() is None:
            raise ValueError("ack_at must be timezone-aware")
        result = await self._session.execute(
            update(AlertDelivery)
            .where(AlertDelivery.id == row_id)
            .values(ack_at=ack_at, updated_at=ack_at)
        )
        if result.rowcount != 1:
            raise ValueError("alert delivery row was not found")

    def _insert_statement(self, row: AlertDeliveryRow) -> Any:
        """Build a dialect-specific INSERT .. ON CONFLICT statement."""
        values = {
            "alert_id": row.pattern_trigger_id,
            "channel": row.channel,
            "status": row.status,
            "telegram_message_id": row.telegram_message_id,
            "error_message": row.error_message,
            "sent_at": row.sent_at,
        }
        if self._dialect == DISPATCH_DELIVERY_DIALECT_POSTGRESQL:
            return (
                postgres_insert(AlertDelivery)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["alert_id", "channel"])
                .returning(AlertDelivery.id)
            )
        if self._dialect == DISPATCH_DELIVERY_DIALECT_SQLITE:
            return (
                sqlite_insert(AlertDelivery)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["alert_id", "channel"])
                .returning(AlertDelivery.id)
            )
        raise NotImplementedError(f"unsupported alert delivery dialect: {self._dialect}")

    async def _existing_row_id(self, *, pattern_trigger_id: int, channel: str) -> int | None:
        """Return existing delivery id for an idempotency conflict."""
        row_id = await self._session.scalar(
            select(AlertDelivery.id).where(
                AlertDelivery.alert_id == pattern_trigger_id,
                AlertDelivery.channel == channel,
            )
        )
        return int(row_id) if row_id is not None else None


def _row_from_orm(row: AlertDelivery) -> AlertDeliveryRow:
    """Map an ORM AlertDelivery row into the dispatch-domain row contract."""
    return AlertDeliveryRow(
        pattern_trigger_id=int(row.alert_id),
        channel=row.channel,
        status=row.status,
        telegram_message_id=row.telegram_message_id,
        error_message=row.error_message,
        sent_at=_ensure_timezone_aware(row.sent_at),
    )


def _ensure_timezone_aware(value: datetime | None) -> datetime | None:
    """Restore UTC tzinfo for SQLite test rows that round-trip as naive."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)
