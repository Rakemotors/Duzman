"""Offline tests for the Alternative.me runtime job."""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from duzman.collectors.alternative_me import AlternativeMeCollector
from duzman.collectors.records import GlobalMetricRecord
from duzman.db.models import GlobalMetric, SourceHealthCheck
from duzman.runtime.alternative_me_jobs import collect_fear_greed_once


class _FakeCollector:
    """Return deterministic Fear & Greed data for runtime job tests."""

    def __init__(self, health_recorder) -> None:
        self.health_recorder = health_recorder

    async def fetch_fear_greed(self):
        """Return one fake global metric record and mark source health."""
        self.health_recorder.mark_success("alternative_me")
        return GlobalMetricRecord(
            ts=datetime(2026, 5, 16, 2, 17, tzinfo=timezone.utc),
            metric_name="fear_greed_index",
            value=Decimal("42"),
        )


@pytest.mark.asyncio
async def test_collect_fear_greed_once_inserts_expected_record():
    """Runtime job should insert one append-only Fear & Greed metric."""
    session = _sqlite_session()

    inserted_count = await collect_fear_greed_once(
        session_factory=lambda: session,
        collector_factory=_FakeCollector,
    )

    metrics = list(session.scalars(select(GlobalMetric)))
    health_checks = list(session.scalars(select(SourceHealthCheck)))
    assert inserted_count == 1
    assert len(metrics) == 1
    assert metrics[0].metric_name == "fear_greed_index"
    assert metrics[0].value == Decimal("42.0000")
    assert health_checks[0].source == "alternative_me"
    assert health_checks[0].status == "ok"


@pytest.mark.asyncio
async def test_collect_fear_greed_once_records_failure_without_insert():
    """Runtime job should commit source failure and skip metric insert on HTTP errors."""
    session = _sqlite_session()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    def collector_factory(health_recorder):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return AlternativeMeCollector(client=client, health_recorder=health_recorder)

    inserted_count = await collect_fear_greed_once(
        session_factory=lambda: session,
        collector_factory=collector_factory,
    )

    assert inserted_count == 0
    assert list(session.scalars(select(GlobalMetric))) == []
    health_checks = list(session.scalars(select(SourceHealthCheck)))
    assert len(health_checks) == 1
    assert health_checks[0].status == "failed"
    assert "status 500" in health_checks[0].error_message


def _sqlite_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SourceHealthCheck.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE global_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts DATETIME NOT NULL,
                    metric_name VARCHAR(30) NOT NULL,
                    value NUMERIC(12, 4)
                )
                """
            )
        )
    return Session(engine)
