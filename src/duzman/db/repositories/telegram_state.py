# src/duzman/db/repositories/telegram_state.py
# Telegram channel state persistence. Stores singleton mute/snooze flags without
# secrets or chat identifiers.
"""Repository for singleton Telegram channel state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import TelegramChannelState


class TelegramStateRepository:
    """Read and mutate Telegram channel enable, mute, and snooze state."""

    async def get_or_create(self, session: AsyncSession, *, now: datetime) -> TelegramChannelState:
        """Return the singleton state row, creating it when absent."""
        row = await session.scalar(select(TelegramChannelState).where(TelegramChannelState.id == 1))
        if row is None:
            row = TelegramChannelState(id=1, enabled=True, muted=False, updated_at=now)
            session.add(row)
            await session.flush()
        return row

    async def set_muted(
        self,
        session: AsyncSession,
        muted: bool,
        *,
        now: datetime,
    ) -> TelegramChannelState:
        """Persist global mute state."""
        row = await self.get_or_create(session, now=now)
        row.muted = muted
        if not muted:
            row.snooze_until = None
        row.updated_at = now
        await session.flush()
        return row

    async def set_snooze_until(
        self,
        session: AsyncSession,
        snooze_until: datetime | None,
        *,
        now: datetime,
    ) -> TelegramChannelState:
        """Persist global snooze deadline."""
        row = await self.get_or_create(session, now=now)
        row.snooze_until = snooze_until
        row.updated_at = now
        await session.flush()
        return row

    async def is_delivery_enabled(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
    ) -> tuple[bool, datetime | None]:
        """Return whether Telegram delivery may send now and the snooze deadline."""
        current = now or datetime.now(UTC)
        row = await self.get_or_create(session, now=current)
        snoozed = row.snooze_until is not None and row.snooze_until > current
        return row.enabled and not row.muted and not snoozed, row.snooze_until
