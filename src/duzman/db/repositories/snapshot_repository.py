"""Read repositories for Pattern Engine metric snapshots."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import (
    EtfFlow,
    FundingRate,
    GlobalMetric,
    Indicator,
    Liquidation,
    OpenInterest,
    PriceSnapshot,
)


class SnapshotReadRepository:
    """Read metric source rows used to build Pattern Engine snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_indicators(
        self,
        assets: Sequence[str],
        since: datetime,
        until: datetime,
    ) -> list[Indicator]:
        """Return fresh indicator rows for the requested assets."""
        statement: Select[tuple[Indicator]] = (
            select(Indicator)
            .where(
                Indicator.asset.in_(assets),
                Indicator.ts >= since,
                Indicator.ts <= until,
            )
            .order_by(Indicator.ts.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def average_indicator_value(
        self,
        asset: str,
        indicator_type: str,
        since: datetime,
        until: datetime,
    ) -> Decimal | None:
        """Return the average value for one indicator in a time window."""
        statement = select(func.avg(Indicator.value)).where(
            Indicator.asset == asset,
            Indicator.indicator_type == indicator_type,
            Indicator.ts >= since,
            Indicator.ts <= until,
            Indicator.value.is_not(None),
        )
        return await self.session.scalar(statement)

    async def latest_price_snapshot(
        self,
        asset: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> PriceSnapshot | None:
        """Return the latest price snapshot for one asset in an optional window."""
        statement: Select[tuple[PriceSnapshot]] = select(PriceSnapshot).where(
            PriceSnapshot.symbol == asset
        )
        if since is not None:
            statement = statement.where(PriceSnapshot.collected_at >= since)
        if until is not None:
            statement = statement.where(PriceSnapshot.collected_at <= until)
        statement = statement.order_by(PriceSnapshot.collected_at.desc()).limit(1)
        return await self.session.scalar(statement)

    async def closest_price_snapshot(
        self,
        asset: str,
        target: datetime,
        tolerance: timedelta = timedelta(hours=12),
    ) -> PriceSnapshot | None:
        """Return the price snapshot closest to a target timestamp."""
        rows = await self.price_snapshots_between(
            asset,
            target - tolerance,
            target + tolerance,
        )
        if not rows:
            return None
        return min(
            rows,
            key=lambda row: abs((_as_utc(row.collected_at) - target).total_seconds()),
        )

    async def price_snapshots_between(
        self,
        asset: str,
        since: datetime,
        until: datetime,
    ) -> list[PriceSnapshot]:
        """Return price snapshots for one asset inside a time window."""
        statement: Select[tuple[PriceSnapshot]] = (
            select(PriceSnapshot)
            .where(
                PriceSnapshot.symbol == asset,
                PriceSnapshot.collected_at >= since,
                PriceSnapshot.collected_at <= until,
            )
            .order_by(PriceSnapshot.collected_at.asc())
        )
        return list((await self.session.scalars(statement)).all())

    async def latest_liquidation(
        self,
        asset: str,
        since: datetime,
        until: datetime,
    ) -> Liquidation | None:
        """Return the latest fresh liquidation row for one asset."""
        statement: Select[tuple[Liquidation]] = (
            select(Liquidation)
            .where(
                Liquidation.asset == asset,
                Liquidation.ts >= since,
                Liquidation.ts <= until,
            )
            .order_by(Liquidation.ts.desc())
            .limit(1)
        )
        return await self.session.scalar(statement)

    async def latest_global_metric(
        self,
        metric_name: str,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> GlobalMetric | None:
        """Return the latest global metric row for one metric name."""
        statement: Select[tuple[GlobalMetric]] = select(GlobalMetric).where(
            GlobalMetric.metric_name == metric_name
        )
        if since is not None:
            statement = statement.where(GlobalMetric.ts >= since)
        if until is not None:
            statement = statement.where(GlobalMetric.ts <= until)
        statement = statement.order_by(GlobalMetric.ts.desc()).limit(1)
        return await self.session.scalar(statement)

    async def closest_global_metric(
        self,
        metric_name: str,
        target: datetime,
        tolerance: timedelta = timedelta(hours=12),
    ) -> GlobalMetric | None:
        """Return the global metric row closest to a target timestamp."""
        statement: Select[tuple[GlobalMetric]] = (
            select(GlobalMetric)
            .where(
                GlobalMetric.metric_name == metric_name,
                GlobalMetric.ts >= target - tolerance,
                GlobalMetric.ts <= target + tolerance,
            )
            .order_by(GlobalMetric.ts.asc())
        )
        rows = list((await self.session.scalars(statement)).all())
        if not rows:
            return None
        return min(
            rows,
            key=lambda row: abs((_as_utc(row.ts) - target).total_seconds()),
        )

    async def funding_rates(
        self,
        asset: str,
        since: datetime,
        until: datetime,
    ) -> list[FundingRate]:
        """Return funding-rate rows for one asset inside a time window."""
        statement: Select[tuple[FundingRate]] = (
            select(FundingRate)
            .where(
                FundingRate.asset == asset,
                FundingRate.ts >= since,
                FundingRate.ts <= until,
                FundingRate.funding_rate_pct.is_not(None),
            )
            .order_by(FundingRate.ts.asc())
        )
        return list((await self.session.scalars(statement)).all())

    async def open_interest_sum(
        self,
        asset: str,
        since: datetime,
        until: datetime,
    ) -> Decimal | None:
        """Return summed open interest for the latest timestamp in a window."""
        latest_ts = await self.session.scalar(
            select(func.max(OpenInterest.ts)).where(
                OpenInterest.asset == asset,
                OpenInterest.ts >= since,
                OpenInterest.ts <= until,
                OpenInterest.oi_usd.is_not(None),
            )
        )
        if latest_ts is None:
            return None
        return await self.session.scalar(
            select(func.sum(OpenInterest.oi_usd)).where(
                OpenInterest.asset == asset,
                OpenInterest.ts == latest_ts,
                OpenInterest.oi_usd.is_not(None),
            )
        )

    async def recent_etf_flows(self, asset: str, limit: int = 30) -> list[EtfFlow]:
        """Return recent ETF flow rows for one asset."""
        statement: Select[tuple[EtfFlow]] = (
            select(EtfFlow)
            .where(EtfFlow.asset == asset, EtfFlow.flow_usd_m.is_not(None))
            .order_by(EtfFlow.date.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(statement)).all())

    async def etf_flow_sum_since(self, asset: str, since_date: date) -> Decimal | None:
        """Return summed ETF flow in millions of USD since a date."""
        return await self.session.scalar(
            select(func.sum(EtfFlow.flow_usd_m)).where(
                and_(
                    EtfFlow.asset == asset,
                    EtfFlow.date >= since_date,
                    EtfFlow.flow_usd_m.is_not(None),
                )
            )
        )


def _as_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime for DB values."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
