from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from duzman.collectors import MarketDataSnapshot
from duzman.db.models import Asset, PriceSnapshot
from duzman.repositories import PriceSnapshotRepository


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


def test_price_snapshot_model_has_required_columns():
    """PriceSnapshot metadata should expose the ingestion persistence columns."""
    columns = set(PriceSnapshot.__table__.columns.keys())

    assert {
        "id",
        "source",
        "symbol",
        "quote_currency",
        "price",
        "collected_at",
        "created_at",
        "raw_payload",
    } <= columns


def test_repository_persists_normalized_binance_snapshot_offline():
    """The repository should persist a Binance snapshot in an offline DB."""
    session = _sqlite_session()
    repository = PriceSnapshotRepository(session)
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)

    saved = repository.create_from_market_data(
        MarketDataSnapshot(
            source="binance",
            symbol="BTC",
            quote_currency="USDT",
            price=Decimal("67123.45"),
            collected_at=collected_at,
            raw_payload={"symbol": "BTCUSDT"},
            volume_24h_quote=Decimal("123456789.12"),
            price_change_24h_pct=Decimal("2.345"),
        )
    )
    session.commit()

    assert saved.id == 1
    assert saved.source == "binance"
    assert saved.symbol == "BTC"
    assert saved.price == Decimal("67123.45000000")
    assert saved.raw_payload == {"symbol": "BTCUSDT"}


def test_repository_persists_normalized_coingecko_snapshot_offline():
    """The repository should persist a CoinGecko snapshot in an offline DB."""
    session = _sqlite_session()
    repository = PriceSnapshotRepository(session)
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)

    saved = repository.create_from_market_data(
        MarketDataSnapshot(
            source="coingecko",
            symbol="ETH",
            quote_currency="USD",
            price=Decimal("3123.45"),
            collected_at=collected_at,
            raw_payload={"id": "ethereum"},
        )
    )
    session.commit()

    assert saved.id == 1
    assert saved.source == "coingecko"
    assert saved.symbol == "ETH"
    assert saved.price == Decimal("3123.45000000")


def test_repository_lists_latest_snapshots_by_source_symbol():
    """Latest queries should return newest snapshots first."""
    session = _sqlite_session()
    repository = PriceSnapshotRepository(session)

    for hour, price in ((10, "67000.00"), (12, "67123.45")):
        repository.create_from_market_data(
            MarketDataSnapshot(
                source="binance",
                symbol="BTC",
                quote_currency="USDT",
                price=Decimal(price),
                collected_at=datetime(2026, 5, 15, hour, 17, tzinfo=timezone.utc),
                raw_payload={"symbol": "BTCUSDT", "lastPrice": price},
            )
        )
    session.commit()

    latest = repository.latest_by_source_symbol("binance", "BTC")

    assert [snapshot.price for snapshot in latest] == [
        Decimal("67123.45000000"),
        Decimal("67000.00000000"),
    ]


def test_repository_lists_latest_snapshots_with_optional_filters():
    """List queries should apply safe source/symbol filters and limits."""
    session = _sqlite_session()
    repository = PriceSnapshotRepository(session)

    for source, symbol, price in (
        ("binance", "BTC", "67123.45"),
        ("coingecko", "BTC", "67120.01"),
        ("binance", "ETH", "3123.45"),
    ):
        repository.create_from_market_data(
            MarketDataSnapshot(
                source=source,
                symbol=symbol,
                quote_currency="USDT" if source == "binance" else "USD",
                price=Decimal(price),
                collected_at=datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc),
                raw_payload={"source": source, "symbol": symbol},
            )
        )
    session.commit()

    latest = repository.list_latest(symbol="BTC", limit=1)

    assert len(latest) == 1
    assert latest[0].symbol == "BTC"
