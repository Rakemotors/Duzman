"""Repositories for liquidation and heatmap persistence."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete
from sqlalchemy.orm import Session

from duzman.collectors.records import HeatmapBucketRecord, LiquidationRecord
from duzman.db.models import Liquidation, LiquidationHeatmap


class LiquidationRepository:
    """Persist normalized hourly liquidation records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_one(self, record: LiquidationRecord) -> Liquidation:
        """Insert one liquidation record and return the ORM row."""
        row = Liquidation(
            ts=record.ts,
            asset=record.asset,
            longs_liquidated_1h_usd=record.longs_1h_usd,
            shorts_liquidated_1h_usd=record.shorts_1h_usd,
            longs_liquidated_24h_usd=record.longs_24h_usd,
            shorts_liquidated_24h_usd=record.shorts_24h_usd,
        )
        self.session.add(row)
        self.session.flush()
        return row


class HeatmapRepository:
    """Replace the current simplified liquidation heatmap for an asset/timeframe."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for(
        self,
        asset: str,
        timeframe: str,
        records: Sequence[HeatmapBucketRecord],
    ) -> int:
        """Atomically replace heatmap buckets for one asset and timeframe."""
        self.session.execute(
            delete(LiquidationHeatmap).where(
                LiquidationHeatmap.asset == asset,
                LiquidationHeatmap.timeframe == timeframe,
            )
        )
        self.session.add_all(
            [
                LiquidationHeatmap(
                    ts=record.ts,
                    asset=record.asset,
                    timeframe=record.timeframe,
                    price_low=record.price_low,
                    price_high=record.price_high,
                    liquidation_volume_usd=record.liquidation_volume_usd,
                )
                for record in records
            ]
        )
        self.session.flush()
        return len(records)
