from datetime import datetime, timezone
from decimal import Decimal

from duzman.collectors import MarketDataSnapshot
from duzman.services import MarketDataService


def test_normalized_market_data_snapshot_is_stable():
    """The normalized snapshot should preserve Decimal price precision."""
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)

    snapshot = MarketDataSnapshot(
        source="binance",
        asset="BTC",
        quote_currency="USDT",
        price_usd=Decimal("67123.45000000"),
        ts=collected_at,
        raw_payload={"symbol": "BTCUSDT"},
    )

    assert snapshot.price_usd == Decimal("67123.45000000")
    assert snapshot.ts == collected_at


def test_market_data_service_normalizes_supported_payloads():
    """The service should normalize static payloads without network access."""
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)
    service = MarketDataService()

    binance_snapshots = service.normalize_binance_tickers(
        [
            {
                "symbol": "BTCUSDT",
                "lastPrice": "67123.45",
                "quoteVolume": "123456789.12",
                "priceChangePercent": "2.345",
            }
        ],
        collected_at,
    )
    coingecko_snapshots = service.normalize_coingecko_markets(
        [
            {
                "id": "bitcoin",
                "symbol": "btc",
                "current_price": 67120.01,
                "total_volume": 456789123.45,
                "price_change_percentage_24h": 2.301,
            }
        ],
        collected_at,
    )

    assert binance_snapshots[0].source == "binance"
    assert binance_snapshots[0].price_usd == Decimal("67123.45")
    assert coingecko_snapshots[0].source == "coingecko"
    assert coingecko_snapshots[0].price_usd == Decimal("67120.01")
