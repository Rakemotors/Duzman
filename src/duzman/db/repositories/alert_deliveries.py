# src/duzman/db/repositories/alert_deliveries.py
# Telegram delivery persistence boundary. Tracks one channel delivery row per
# AlertGate PatternTrigger alert.
"""Repository for Telegram alert delivery state."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import AlertDelivery, PatternTrigger

TELEGRAM_CHANNEL = "telegram"
TERMINAL_STATUSES = {"sent", "snoozed", "acked"}


class AlertDeliveryRepository:
    """Read and write per-alert Telegram delivery rows."""

    async def get_by_alert(
        self,
        session: AsyncSession,
        alert_id: int,
        channel: str = TELEGRAM_CHANNEL,
    ) -> AlertDelivery | None:
        """Return the delivery row for one alert/channel pair, if present."""
        statement = select(AlertDelivery).where(
            AlertDelivery.alert_id == alert_id,
            AlertDelivery.channel == channel,
        )
        return cast(AlertDelivery | None, await session.scalar(statement))

    async def create_or_update(
        self,
        session: AsyncSession,
        alert_id: int,
        status: str,
        *,
        channel: str = TELEGRAM_CHANNEL,
        sent_at: datetime | None = None,
        ack_at: datetime | None = None,
        snooze_until: datetime | None = None,
        error_message: str | None = None,
        now: datetime,
    ) -> AlertDelivery:
        """Upsert a delivery row and return the current ORM object."""
        row = await self.get_by_alert(session, alert_id, channel)
        if row is None:
            row = AlertDelivery(
                alert_id=alert_id,
                channel=channel,
                status=status,
                sent_at=sent_at,
                ack_at=ack_at,
                snooze_until=snooze_until,
                error_message=error_message,
                updated_at=now,
            )
            session.add(row)
        else:
            row.status = status
            row.sent_at = sent_at
            row.ack_at = ack_at
            row.snooze_until = snooze_until
            row.error_message = error_message
            row.updated_at = now
        await session.flush()
        return row

    async def list_pending_alerts(
        self,
        session: AsyncSession,
        *,
        limit: int = 20,
        channel: str = TELEGRAM_CHANNEL,
    ) -> list[PatternTrigger]:
        """Return ALLOW PatternTrigger alerts that have no terminal delivery."""
        statement = (
            self._undelivered_allow_statement(session, channel)
            .order_by(PatternTrigger.ts)
            .limit(limit)
        )
        return list(await session.scalars(statement))

    async def list_unsent_since(
        self,
        session: AsyncSession,
        *,
        since: datetime,
        limit: int = 50,
        channel: str = TELEGRAM_CHANNEL,
    ) -> list[PatternTrigger]:
        """Return recent ALLOW alerts without successful Telegram delivery."""
        _assert_aware_utc(since, "since")
        statement = (
            self._undelivered_allow_statement(session, channel)
            .where(PatternTrigger.ts >= since)
            .order_by(PatternTrigger.ts)
            .limit(limit)
        )
        return list(await session.scalars(statement))

    async def list_recent_alerts(
        self,
        session: AsyncSession,
        *,
        limit: int = 5,
    ) -> list[PatternTrigger]:
        """Return recent AlertGate trigger rows for command output."""
        statement = select(PatternTrigger).order_by(PatternTrigger.ts.desc()).limit(limit)
        return list(await session.scalars(statement))

    async def last_alert_ts(self, session: AsyncSession) -> datetime | None:
        """Return the newest AlertGate trigger timestamp."""
        return await session.scalar(select(func.max(PatternTrigger.ts)))

    async def last_successful_send_ts(
        self,
        session: AsyncSession,
        channel: str = TELEGRAM_CHANNEL,
    ) -> datetime | None:
        """Return the newest successful delivery timestamp."""
        return await session.scalar(
            select(func.max(AlertDelivery.sent_at)).where(
                AlertDelivery.channel == channel,
                AlertDelivery.status == "sent",
            )
        )

    def _undelivered_allow_statement(
        self,
        session: AsyncSession,
        channel: str,
    ) -> Select[tuple[PatternTrigger]]:
        """Build the common query for ALLOW alerts not already delivered."""
        return (
            select(PatternTrigger)
            .outerjoin(
                AlertDelivery,
                (AlertDelivery.alert_id == PatternTrigger.id)
                & (AlertDelivery.channel == channel),
            )
            .where(
                _gate_decision_expr(_dialect_name(session)) == "ALLOW",
                or_(
                    AlertDelivery.id.is_(None),
                    AlertDelivery.status.not_in(TERMINAL_STATUSES),
                ),
            )
        )


def _gate_decision_expr(dialect_name: str) -> ColumnElement[str]:
    """Return a portable JSON expression for pattern trigger gate decisions."""
    if dialect_name == "sqlite":
        return func.json_extract(PatternTrigger.conditions_snapshot, "$.gate_decision")
    return PatternTrigger.conditions_snapshot.op("->>")("gate_decision")


def _dialect_name(session: AsyncSession) -> str:
    """Return the bound SQL dialect name for an async session."""
    return session.get_bind().dialect.name


def _assert_aware_utc(ts: datetime, field_name: str) -> None:
    """Assert that a repository timestamp is timezone-aware UTC."""
    assert ts.tzinfo is not None and ts.utcoffset() is not None, (
        f"{field_name} must be timezone-aware UTC"
    )
    assert ts.utcoffset() == timedelta(0), f"{field_name} must be UTC"
