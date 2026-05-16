"""Manual runtime jobs for public CoinGlass liquidation metrics."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from duzman.collectors.coinglass import CoinGlassCollector
from duzman.db.models import Asset, PriceSnapshot
from duzman.db.repositories import HeatmapRepository, LiquidationRepository
from duzman.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    safe_error_message,
)
from duzman.repositories import SourceHealthRepository


SessionFactory = Callable[[], Session]
LiquidationCollectorFactory = Callable[["_CoinGlassHealthRecorder"], CoinGlassCollector]
HeatmapCollectorFactory = Callable[
    ["_CoinGlassHealthRecorder", Callable[[str], Decimal | None]],
    CoinGlassCollector,
]

COINGLASS_HEATMAP_ASSETS = ("BTC", "ETH")
COINGLASS_HEATMAP_TIMEFRAMES = ("24h", "7d")

LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


class _CoinGlassHealthRecorder:
    """Adapt CoinGlass health calls to the existing source health repository."""

    def __init__(self, repository: SourceHealthRepository) -> None:
        self.repository = repository

    def mark_success(self, source: str) -> None:
        """Record a successful CoinGlass source check."""
        self.repository.record_success(source=source, latency_ms=0)

    def mark_failure(self, source: str, error: str) -> None:
        """Record a failed CoinGlass source check."""
        self.repository.record_failure(source=source, error_message=error)


async def collect_liquidations_once(
    session_factory: SessionFactory | None = None,
    collector_factory: LiquidationCollectorFactory | None = None,
) -> int:
    """Collect and persist one hourly CoinGlass liquidation batch."""
    session = _open_session(session_factory)
    logger = get_logger(__name__)
    log_event(logger, "coinglass_liquidations_collection_started")
    try:
        repository = LiquidationRepository(session)
        health_recorder = _CoinGlassHealthRecorder(SourceHealthRepository(session))
        collector = (
            collector_factory(health_recorder)
            if collector_factory is not None
            else CoinGlassCollector(health_recorder=health_recorder)
        )
        inserted_count = 0
        for asset in _enabled_assets(session):
            record = await collector.fetch_liquidations_1h(asset)
            if record is None:
                continue
            repository.insert_one(record)
            inserted_count += 1
        session.commit()
    except Exception as exc:
        session.rollback()
        log_event(
            logger,
            "coinglass_liquidations_collection_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        raise
    finally:
        session.close()

    log_event(
        logger,
        "coinglass_liquidations_collection_completed",
        inserted_count=inserted_count,
    )
    return inserted_count


async def collect_heatmaps_once(
    session_factory: SessionFactory | None = None,
    collector_factory: HeatmapCollectorFactory | None = None,
) -> int:
    """Collect and replace simplified CoinGlass liquidation heatmaps."""
    session = _open_session(session_factory)
    logger = get_logger(__name__)
    log_event(logger, "coinglass_heatmap_collection_started")
    try:
        repository = HeatmapRepository(session)
        health_recorder = _CoinGlassHealthRecorder(SourceHealthRepository(session))
        price_provider = lambda asset: _latest_price(session, asset)
        collector = (
            collector_factory(health_recorder, price_provider)
            if collector_factory is not None
            else CoinGlassCollector(
                health_recorder=health_recorder,
                current_price_provider=price_provider,
            )
        )
        inserted_count = 0
        enabled_assets = set(_enabled_assets(session))
        for asset in COINGLASS_HEATMAP_ASSETS:
            if asset not in enabled_assets:
                continue
            for timeframe in COINGLASS_HEATMAP_TIMEFRAMES:
                records = await collector.fetch_heatmap(asset, timeframe)
                if not records:
                    continue
                inserted_count += repository.replace_for(asset, timeframe, records)
        session.commit()
    except Exception as exc:
        session.rollback()
        log_event(
            logger,
            "coinglass_heatmap_collection_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        raise
    finally:
        session.close()

    log_event(
        logger,
        "coinglass_heatmap_collection_completed",
        inserted_count=inserted_count,
    )
    return inserted_count


def main(argv: Sequence[str] | None = None) -> int:
    """Run one CoinGlass liquidation and heatmap collection cycle."""
    args = _build_parser().parse_args(list(argv or ()))
    configure_logging(level=LOG_LEVELS[args.log_level])
    try:
        import asyncio

        asyncio.run(collect_liquidations_once())
        asyncio.run(collect_heatmaps_once())
    except Exception as exc:
        log_event(
            get_logger(__name__),
            "coinglass_command_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        return 1
    return 0


def _open_session(session_factory: SessionFactory | None) -> Session:
    if session_factory is None:
        from duzman.db.session import get_session_factory

        return get_session_factory()()
    return session_factory()


def _enabled_assets(session: Session) -> list[str]:
    statement = (
        select(Asset.symbol)
        .where(Asset.enabled.is_(True))
        .order_by(Asset.symbol)
    )
    return list(session.scalars(statement))


def _latest_price(session: Session, asset: str) -> Decimal | None:
    statement = (
        select(PriceSnapshot.price)
        .where(PriceSnapshot.symbol == asset)
        .order_by(PriceSnapshot.collected_at.desc())
        .limit(1)
    )
    return session.scalars(statement).first()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect one public CoinGlass liquidation batch.",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(LOG_LEVELS),
        default="INFO",
        help="Runtime log level for the CoinGlass command.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
