"""Offline tests for the Farside ETF flow runtime job."""

from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from duzman.collectors.farside import FarsideCollector
from duzman.collectors.records import ETFFlowRecord
from duzman.db.models import Asset, EtfFlow, SourceHealthCheck
from duzman.runtime.farside_jobs import collect_etf_flows_once


class _FakeCollector:
    """Return deterministic ETF flow records for runtime job tests."""

    def __init__(self, health_recorder) -> None:
        self.health_recorder = health_recorder
        self.assets: list[str] = []

    async def fetch_etf_flows(self, assets):
        """Return one fake record and mark Farside as healthy."""
        self.assets = list(assets)
        self.health_recorder.mark_success("farside")
        return [
            ETFFlowRecord(
                date=date(2026, 5, 16),
                asset="BTC",
                provider="TOTAL",
                flow_usd_m=Decimal("77.8"),
            )
        ]


@pytest.mark.asyncio
async def test_collect_etf_flows_once_upserts_expected_records():
    """Runtime job should fetch enabled ETF assets and upsert records."""
    session = _sqlite_session()

    inserted_count = await collect_etf_flows_once(
        session_factory=lambda: session,
        collector_factory=_FakeCollector,
    )

    flows = list(session.scalars(select(EtfFlow)))
    health_checks = list(session.scalars(select(SourceHealthCheck)))
    assert inserted_count == 1
    assert len(flows) == 1
    assert flows[0].asset == "BTC"
    assert flows[0].provider == "TOTAL"
    assert flows[0].flow_usd_m == Decimal("77.80")
    assert len(health_checks) == 1
    assert health_checks[0].source == "farside"
    assert health_checks[0].status == "ok"


@pytest.mark.asyncio
async def test_collect_etf_flows_once_uses_only_enabled_btc_eth_assets():
    """Runtime job should ignore disabled or non-ETF assets."""
    session = _sqlite_session()
    captured_collector: _FakeCollector | None = None

    def collector_factory(health_recorder):
        nonlocal captured_collector
        captured_collector = _FakeCollector(health_recorder)
        return captured_collector

    await collect_etf_flows_once(
        session_factory=lambda: session,
        collector_factory=collector_factory,
    )

    assert captured_collector is not None
    assert captured_collector.assets == ["BTC"]


@pytest.mark.asyncio
async def test_collect_etf_flows_once_records_failure_on_http_500():
    """HTTP failure through the real collector should mark Farside failed."""
    session = _sqlite_session()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    def collector_factory(health_recorder):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return FarsideCollector(client=client, health_recorder=health_recorder)

    inserted_count = await collect_etf_flows_once(
        session_factory=lambda: session,
        collector_factory=collector_factory,
    )

    health_checks = list(session.scalars(select(SourceHealthCheck)))
    assert inserted_count == 0
    assert len(health_checks) == 1
    assert health_checks[0].source == "farside"
    assert health_checks[0].status == "failed"
    assert "status 500" in health_checks[0].error_message


def _sqlite_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    EtfFlow.__table__.create(engine)
    SourceHealthCheck.__table__.create(engine)
    session = Session(engine)
    session.add_all(
        [
            Asset(symbol="BTC", name="Bitcoin", enabled=True),
            Asset(symbol="ETH", name="Ethereum", enabled=False),
            Asset(symbol="SOL", name="Solana", enabled=True),
        ]
    )
    session.commit()
    return session
