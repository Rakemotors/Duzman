from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from duzman.collectors import MarketDataSnapshot
from duzman.repositories import PriceSnapshotRepository
from duzman.services.market_data_fetchers import PublicMarketDataFetcher
from duzman.services.source_health_tracking import SourceHealthTrackingService


DEFAULT_BINANCE_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
DEFAULT_COINGECKO_COIN_IDS: tuple[str, ...] = ("bitcoin", "ethereum")


@dataclass(frozen=True)
class MarketDataCollectionResult:
    """Summary of one explicit public market data collection cycle."""

    started_at: datetime
    finished_at: datetime
    attempted_sources: tuple[str, ...]
    successful_sources: tuple[str, ...]
    failed_sources: tuple[str, ...]
    snapshots_created: int
    health_checks_created: int
    errors: dict[str, str] = field(default_factory=dict)


class MarketDataCollectionJob:
    """Run one public fetch, price persistence, and source health cycle."""

    def __init__(
        self,
        session: Session,
        fetcher: PublicMarketDataFetcher | None = None,
        price_snapshot_repository: PriceSnapshotRepository | None = None,
        source_health_tracker: SourceHealthTrackingService | None = None,
    ) -> None:
        self.session = session
        self.fetcher = fetcher or PublicMarketDataFetcher()
        self.price_snapshot_repository = (
            price_snapshot_repository or PriceSnapshotRepository(session)
        )
        self.source_health_tracker = (
            source_health_tracker or SourceHealthTrackingService(session)
        )

    def run(
        self,
        binance_symbols: Sequence[str] = DEFAULT_BINANCE_SYMBOLS,
        coingecko_coin_ids: Sequence[str] = DEFAULT_COINGECKO_COIN_IDS,
        collected_at: datetime | None = None,
    ) -> MarketDataCollectionResult:
        """Run one collection cycle without starting a scheduler."""
        started_at = datetime.now(timezone.utc)
        snapshot_time = collected_at or started_at
        attempted_sources: list[str] = []
        successful_sources: list[str] = []
        failed_sources: list[str] = []
        errors: dict[str, str] = {}
        snapshots_created = 0
        health_checks_created = 0

        source_plan = (
            (
                "binance",
                lambda: [
                    self.fetcher.fetch_binance_ticker(symbol, snapshot_time)
                    for symbol in binance_symbols
                ],
            ),
            (
                "coingecko",
                lambda: [
                    self.fetcher.fetch_coingecko_market(coin_id, snapshot_time)
                    for coin_id in coingecko_coin_ids
                ],
            ),
        )

        for source, fetch_snapshots in source_plan:
            attempted_sources.append(source)
            health_checks_created += 1
            health_result = self.source_health_tracker.track_fetch(
                source,
                fetch_snapshots,
            )
            if not health_result.ok:
                failed_sources.append(source)
                errors[source] = health_result.error_message or "unknown error"
                continue

            created_for_source = self._persist_snapshots(health_result.value or ())
            snapshots_created += created_for_source
            successful_sources.append(source)

        finished_at = datetime.now(timezone.utc)
        return MarketDataCollectionResult(
            started_at=started_at,
            finished_at=finished_at,
            attempted_sources=tuple(attempted_sources),
            successful_sources=tuple(successful_sources),
            failed_sources=tuple(failed_sources),
            snapshots_created=snapshots_created,
            health_checks_created=health_checks_created,
            errors=errors,
        )

    def _persist_snapshots(self, snapshots: Sequence[MarketDataSnapshot]) -> int:
        for snapshot in snapshots:
            self.price_snapshot_repository.create_from_market_data(snapshot)
        self.session.commit()
        return len(snapshots)


def run_public_market_data_ingestion_job(
    session: Session,
    fetcher: PublicMarketDataFetcher | None = None,
    binance_symbols: Sequence[str] = DEFAULT_BINANCE_SYMBOLS,
    coingecko_coin_ids: Sequence[str] = DEFAULT_COINGECKO_COIN_IDS,
) -> MarketDataCollectionResult:
    """Run the explicit Stage A public market data ingestion job."""
    return MarketDataCollectionJob(session=session, fetcher=fetcher).run(
        binance_symbols=binance_symbols,
        coingecko_coin_ids=coingecko_coin_ids,
    )

