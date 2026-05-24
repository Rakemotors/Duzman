"""Tests for persisting deterministic indicator records and the #72 FK invariant."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from duzman.db.models import Asset, Indicator
from duzman.indicators import IndicatorRecord
from duzman.repositories import IndicatorRepository


@pytest.mark.asyncio
async def test_indicator_repository_saves_indicator_records():
    """Repository should persist supplied indicator records."""
    session = _sqlite_session()
    repository = IndicatorRepository()

    inserted_count = await repository.save_indicators(session, [_indicator_record()])
    session.commit()

    indicators = list(session.scalars(select(Indicator)))
    assert inserted_count == 1
    assert len(indicators) == 1
    assert indicators[0].asset == "BTC"
    assert indicators[0].indicator_type == "rsi"


@pytest.mark.asyncio
async def test_indicator_repository_returns_zero_for_empty_records():
    """Repository should no-op for an empty record list."""
    session = _sqlite_session()
    repository = IndicatorRepository()

    inserted_count = await repository.save_indicators(session, [])

    assert inserted_count == 0
    assert list(session.scalars(select(Indicator))) == []


@pytest.mark.asyncio
async def test_indicator_repository_persists_indicator_value_and_timeframe():
    """Repository should preserve indicator value and timeframe fields."""
    session = _sqlite_session()
    repository = IndicatorRepository()

    await repository.save_indicators(session, [_indicator_record(value=Decimal("42.1234"))])
    session.commit()

    indicator = session.scalars(select(Indicator)).one()
    assert indicator.timeframe == "1h"
    assert indicator.value == Decimal("42.1234")


@pytest.mark.asyncio
async def test_indicator_repository_persists_parameters_dict():
    """Repository should persist JSON-compatible indicator parameters."""
    session = _sqlite_session()
    repository = IndicatorRepository()

    await repository.save_indicators(
        session,
        [_indicator_record(parameters={"period": 14, "source": "test"})],
    )
    session.commit()

    indicator = session.scalars(select(Indicator)).one()
    assert indicator.parameters == {"period": 14, "source": "test"}


@pytest.mark.asyncio
async def test_indicator_repository_raises_integrity_error_without_asset():
    """Missing assets must surface as an FK IntegrityError for Issue #72."""
    session = _sqlite_session(seed_asset=False)
    repository = IndicatorRepository()

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        await repository.save_indicators(session, [_indicator_record()])


@pytest.mark.asyncio
async def test_indicator_repository_saves_indicator_when_asset_exists():
    """Pre-existing assets are required before indicator persistence."""
    session = _sqlite_session(seed_asset=True)
    repository = IndicatorRepository()

    await repository.save_indicators(session, [_indicator_record(value=Decimal("50.0"))])
    session.commit()

    indicator_count = session.scalar(select(func.count()).select_from(Indicator))
    assert indicator_count == 1


def _sqlite_session(seed_asset: bool = True) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(connection, _connection_record):
        connection.execute("PRAGMA foreign_keys=ON")

    Asset.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE indicators (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts DATETIME NOT NULL,
                    asset VARCHAR(10) NOT NULL,
                    indicator_type VARCHAR(20) NOT NULL,
                    timeframe VARCHAR(10),
                    value NUMERIC(12, 4),
                    parameters JSON,
                    FOREIGN KEY(asset) REFERENCES assets(symbol)
                )
                """
            )
        )
    session = Session(engine)
    if seed_asset:
        session.add(Asset(symbol="BTC", name="Bitcoin"))
        session.commit()
    return session


def _indicator_record(
    value: Decimal = Decimal("70.0000"),
    parameters: dict | None = None,
) -> IndicatorRecord:
    return IndicatorRecord(
        ts=datetime(2026, 5, 16, 12, 23, tzinfo=UTC),
        asset="BTC",
        indicator_type="rsi",
        timeframe="1h",
        value=value,
        parameters=parameters or {"period": 14},
    )
