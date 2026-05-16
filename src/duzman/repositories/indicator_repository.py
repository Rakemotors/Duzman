"""Repository for persisting deterministic indicator records."""

from __future__ import annotations

import inspect
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from duzman.db.models import Indicator
from duzman.indicators import IndicatorRecord


class IndicatorRepository:
    """Persist deterministic indicator values into the indicators table."""

    async def save_indicators(
        self,
        session: AsyncSession | Session,
        records: Sequence[IndicatorRecord],
    ) -> int:
        """Insert indicator records and return the number of inserted rows."""
        if not records:
            return 0

        session.add_all(
            [
                Indicator(
                    ts=record.ts,
                    asset=record.asset,
                    indicator_type=record.indicator_type,
                    timeframe=record.timeframe,
                    value=record.value,
                    parameters=dict(record.parameters),
                )
                for record in records
            ]
        )
        flush_result = session.flush()
        if inspect.isawaitable(flush_result):
            await flush_result
        return len(records)
