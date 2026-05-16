from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from duzman.api import create_app
from duzman.api.dependencies import get_api_db
from duzman.collectors import MarketDataSnapshot
from duzman.db.models import Asset, PriceSnapshot, SourceHealthCheck
from duzman.repositories import PriceSnapshotRepository, SourceHealthRepository
from duzman.runtime.verify_read_only_api import verify_read_only_api_app


def _api_client_with_seed_data(
    collected_at: datetime | None = None,
) -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    PriceSnapshot.__table__.create(engine)
    SourceHealthCheck.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)

    snapshot_time = collected_at or datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)
    second_snapshot_time = snapshot_time + timedelta(minutes=1)

    with Session(engine) as session:
        session.add_all(
            [
                Asset(symbol="BTC", name="Bitcoin"),
                Asset(symbol="ETH", name="Ethereum"),
            ]
        )
        session.commit()
        price_repository = PriceSnapshotRepository(session)
        price_repository.create_from_market_data(
            MarketDataSnapshot(
                source="binance",
                symbol="BTC",
                quote_currency="USDT",
                price=Decimal("67123.45"),
                collected_at=snapshot_time,
                raw_payload={"symbol": "BTCUSDT", "lastPrice": "67123.45"},
                volume_24h_quote=Decimal("123456789.12"),
                price_change_24h_pct=Decimal("2.345"),
            )
        )
        price_repository.create_from_market_data(
            MarketDataSnapshot(
                source="coingecko",
                symbol="ETH",
                quote_currency="USD",
                price=Decimal("3120.01"),
                collected_at=second_snapshot_time,
                raw_payload={"id": "ethereum"},
            )
        )
        health_repository = SourceHealthRepository(session)
        health_repository.record_success(
            "binance",
            latency_ms=25,
            checked_at=snapshot_time,
        )
        health_repository.record_failure(
            "coingecko",
            error_message="password=fake-secret",
            latency_ms=100,
            checked_at=second_snapshot_time,
        )
        session.commit()

    app = create_app()

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_api_db] = override_db
    return TestClient(app), session_factory


def _api_client_without_seed_data() -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Asset.__table__.create(engine)
    PriceSnapshot.__table__.create(engine)
    SourceHealthCheck.__table__.create(engine)
    session_factory = sessionmaker(bind=engine)
    app = create_app()

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_api_db] = override_db
    return TestClient(app)


def test_latest_price_snapshots_endpoint_returns_read_only_data_shape():
    """Latest price snapshots should expose normalized fields without raw payloads."""
    client, _ = _api_client_with_seed_data()

    response = client.get("/api/market-data/prices/latest")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert set(payload[0]) == {
        "symbol",
        "source",
        "quote_currency",
        "price",
        "collected_at",
        "created_at",
        "volume_24h_quote",
        "price_change_24h_pct",
    }
    assert "raw_payload" not in payload[0]


def test_latest_price_snapshots_endpoint_filters_and_bounds_limit():
    """Price snapshot filters should be deterministic and limit-bounded."""
    client, _ = _api_client_with_seed_data()

    filtered = client.get(
        "/api/market-data/prices/latest",
        params={"symbol": "BTC", "source": "binance", "limit": 1},
    )
    too_large = client.get(
        "/api/market-data/prices/latest",
        params={"limit": 101},
    )

    assert filtered.status_code == 200
    assert filtered.json()[0]["symbol"] == "BTC"
    assert filtered.json()[0]["source"] == "binance"
    assert too_large.status_code == 422


def test_source_health_endpoint_returns_redacted_latest_status():
    """Source health responses should redact persisted error summaries."""
    client, _ = _api_client_with_seed_data()

    response = client.get(
        "/api/market-data/source-health",
        params={"source": "coingecko"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["source"] == "coingecko"
    assert payload[0]["status"] == "failed"
    assert payload[0]["error_message"] == "password=<redacted>"


def test_ingestion_status_endpoint_returns_summary():
    """Ingestion status should summarize persisted records without side effects."""
    client, _ = _api_client_with_seed_data()

    response = client.get("/api/market-data/ingestion-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["price_snapshot_count"] == 2
    assert payload["source_health_check_count"] == 2
    assert payload["sources_seen"] == ["binance", "coingecko"]
    assert payload["symbols_seen"] == ["BTC", "ETH"]
    assert payload["latest_price_snapshot_at"] is not None
    assert payload["latest_source_health_check_at"] is not None


def test_ingestion_alerts_endpoint_returns_deterministic_alerts():
    """Ingestion alerts should be derived only from persisted local rows."""
    client, _ = _api_client_with_seed_data(
        collected_at=datetime.now(timezone.utc) - timedelta(minutes=2)
    )

    response = client.get("/api/market-data/ingestion-alerts")

    assert response.status_code == 200
    payload = response.json()
    assert [alert["alert_type"] for alert in payload] == ["source_recent_failure"]
    assert payload[0]["source"] == "coingecko"
    assert payload[0]["severity"] == "critical"
    assert "password" not in str(payload)


def test_ingestion_alerts_endpoint_reports_missing_persisted_data():
    """Empty local tables should produce missing-data alerts without side effects."""
    client = _api_client_without_seed_data()

    response = client.get("/api/market-data/ingestion-alerts")

    assert response.status_code == 200
    assert {alert["alert_type"] for alert in response.json()} == {
        "no_price_snapshots",
        "no_source_health_checks",
    }


def test_market_data_api_rejects_write_methods():
    """Market data API routes should remain read-only."""
    client, _ = _api_client_with_seed_data()

    response = client.post("/api/market-data/prices/latest", json={})

    assert response.status_code == 405


def test_market_data_api_does_not_start_scheduler_or_fetch_network(monkeypatch):
    """Read-only API calls should not start schedulers or call public fetchers."""
    import duzman.runtime.market_data_scheduler as scheduler_runtime
    from duzman.services.public_http_client import PublicHttpClient

    def fail_if_scheduler_runs(*args, **kwargs):
        raise AssertionError("read-only API must not start schedulers")

    def fail_if_network_runs(*args, **kwargs):
        raise AssertionError("read-only API must not call public HTTP")

    monkeypatch.setattr(
        scheduler_runtime,
        "run_market_data_scheduler_forever",
        fail_if_scheduler_runs,
    )
    monkeypatch.setattr(PublicHttpClient, "get_json", fail_if_network_runs)

    client, _ = _api_client_with_seed_data()

    assert client.get("/api/market-data/ingestion-status").status_code == 200
    assert client.get("/api/market-data/ingestion-alerts").status_code == 200


def test_api_app_creation_registers_routes_without_runtime_side_effects(monkeypatch):
    """App creation should register routes without scheduler or public HTTP work."""
    import duzman.runtime.market_data_scheduler as scheduler_runtime
    from duzman.services.public_http_client import PublicHttpClient

    def fail_if_scheduler_runs(*args, **kwargs):
        raise AssertionError("API app creation must not start schedulers")

    def fail_if_network_runs(*args, **kwargs):
        raise AssertionError("API app creation must not call public HTTP")

    monkeypatch.setattr(
        scheduler_runtime,
        "run_market_data_scheduler_forever",
        fail_if_scheduler_runs,
    )
    monkeypatch.setattr(PublicHttpClient, "get_json", fail_if_network_runs)

    routes = verify_read_only_api_app()

    assert routes == (
        "/api/market-data/ingestion-alerts",
        "/api/market-data/ingestion-status",
        "/api/market-data/prices/latest",
        "/api/market-data/source-health",
    )
