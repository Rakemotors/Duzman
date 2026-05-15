from collections.abc import Mapping

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from duzman.collectors import MarketDataSnapshot
from duzman.db.models import PriceSnapshot


class PriceSnapshotRepository:
    """Persist and query normalized public market price snapshots."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_from_market_data(
        self, snapshot: MarketDataSnapshot
    ) -> PriceSnapshot:
        """Persist one normalized market data snapshot."""
        price_snapshot = PriceSnapshot(
            source=snapshot.source,
            symbol=snapshot.symbol,
            quote_currency=snapshot.quote_currency,
            price=snapshot.price,
            collected_at=snapshot.collected_at,
            raw_payload=self._safe_raw_payload(snapshot.raw_payload),
            volume_24h_quote=snapshot.volume_24h_quote,
            price_change_24h_pct=snapshot.price_change_24h_pct,
        )
        self.session.add(price_snapshot)
        self.session.flush()
        self.session.refresh(price_snapshot)
        return price_snapshot

    def latest_by_source_symbol(
        self, source: str, symbol: str, limit: int = 10
    ) -> list[PriceSnapshot]:
        """Return latest snapshots for one source and asset symbol."""
        statement: Select[tuple[PriceSnapshot]] = (
            select(PriceSnapshot)
            .where(PriceSnapshot.source == source, PriceSnapshot.symbol == symbol)
            .order_by(PriceSnapshot.collected_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def _safe_raw_payload(self, raw_payload: Mapping[str, object]) -> dict[str, object]:
        return dict(raw_payload)

