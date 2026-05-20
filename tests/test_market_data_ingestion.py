from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from duzman.collectors import MarketDataPayloadError
from duzman.db.models import Asset, PriceSnapshot
from duzman.services import MarketDataIngestionService


def _sqlite_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    PriceSnapshot.__table__.create(engine)
    session = Session(engine)
    session.add_all(
        [
            Asset(symbol="BTC", name="Bitcoin"),
            Asset(symbol="ETH", name="Ethereum"),
        ]
    )
    session.commit()
    return session


def test_ingestion_service_saves_supplied_static_payloads_offline():
    """Static public payloads should normalize and persist without network access."""
    session = _sqlite_session()
    service = MarketDataIngestionService(session)
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)

    result = service.ingest_supplied_payloads(
        binance_payloads=[
            {
                "symbol": "BTCUSDT",
                "lastPrice": "67123.45",
                "quoteVolume": "123456789.12",
                "priceChangePercent": "2.345",
            }
        ],
        coingecko_payloads=[
            {
                "id": "ethereum",
                "symbol": "eth",
                "current_price": 3123.45,
                "total_volume": 987654321.12,
                "price_change_percentage_24h": -1.25,
            }
        ],
        collected_at=collected_at,
    )

    saved = list(session.scalars(select(PriceSnapshot)))

    assert result.saved_count == 2
    assert {snapshot.source for snapshot in saved} == {"binance", "coingecko"}
    assert {snapshot.asset for snapshot in saved} == {"BTC", "ETH"}


def test_ingestion_rejects_malformed_payload_without_persisting():
    """Malformed payloads should fail before any bad data is committed."""
    session = _sqlite_session()
    service = MarketDataIngestionService(session)

    with pytest.raises(MarketDataPayloadError, match="lastPrice"):
        service.ingest_supplied_payloads(
            binance_payloads=[{"symbol": "BTCUSDT"}],
        )

    saved_count = session.scalar(select(func.count()).select_from(PriceSnapshot))

    assert saved_count == 0
