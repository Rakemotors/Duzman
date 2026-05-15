from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from duzman.db.models import PriceSnapshot
from duzman.repositories import PriceSnapshotRepository
from duzman.services.market_data import MarketDataService


@dataclass(frozen=True)
class MarketDataIngestionResult:
    """Summary of one offline-safe market data ingestion run."""

    saved_count: int
    saved_snapshots: tuple[PriceSnapshot, ...]


class MarketDataIngestionService:
    """Normalize supplied public market payloads and persist price snapshots."""

    def __init__(
        self,
        session: Session,
        market_data_service: MarketDataService | None = None,
        repository: PriceSnapshotRepository | None = None,
    ) -> None:
        self.session = session
        self.market_data_service = market_data_service or MarketDataService()
        self.repository = repository or PriceSnapshotRepository(session)

    def ingest_supplied_payloads(
        self,
        binance_payloads: Iterable[Mapping[str, Any]] = (),
        coingecko_payloads: Iterable[Mapping[str, Any]] = (),
        collected_at: datetime | None = None,
    ) -> MarketDataIngestionResult:
        """Persist normalized snapshots from caller-supplied static payloads."""
        normalized_snapshots = [
            *self.market_data_service.normalize_binance_tickers(
                binance_payloads, collected_at
            ),
            *self.market_data_service.normalize_coingecko_markets(
                coingecko_payloads, collected_at
            ),
        ]
        saved_snapshots = tuple(
            self.repository.create_from_market_data(snapshot)
            for snapshot in normalized_snapshots
        )
        self.session.commit()
        return MarketDataIngestionResult(
            saved_count=len(saved_snapshots),
            saved_snapshots=saved_snapshots,
        )
