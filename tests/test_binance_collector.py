"""Offline tests for the Binance public spot collector."""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from duzman.collectors import BinanceCollector, MarketDataPayloadError


class _HealthRecorder:
    """Capture source-health writes without using a database."""

    def __init__(self) -> None:
        self.successes: list[tuple[str, int]] = []
        self.failures: list[tuple[str, str, int | None]] = []

    def record_success(self, source: str, latency_ms: int) -> None:
        """Record a fake successful source-health event."""
        self.successes.append((source, latency_ms))

    def record_failure(
        self,
        source: str,
        error_message: str,
        latency_ms: int | None = None,
    ) -> None:
        """Record a fake failed source-health event."""
        self.failures.append((source, error_message, latency_ms))


@pytest.mark.asyncio
async def test_fetch_tickers_happy_path_normalizes_snapshot():
    """Ticker fetch should normalize Binance 24hr fields without auth headers."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        assert "X-MBX-APIKEY" not in request.headers
        return httpx.Response(200, json=_ticker_payload("BTCUSDT"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshots = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_tickers(["BTC"])

    assert len(snapshots) == 1
    assert snapshots[0].source == "binance"
    assert snapshots[0].asset == "BTC"
    assert snapshots[0].quote_currency == "USDT"
    assert snapshots[0].price_usd == Decimal("67123.45")
    assert snapshots[0].volume_24h_quote == Decimal("123456789.12")
    assert snapshots[0].price_change_24h_pct == Decimal("2.345")
    assert snapshots[0].raw_payload["symbol"] == "BTCUSDT"
    assert observed_requests[0].url.path == "/api/v3/ticker/24hr"
    assert observed_requests[0].url.params["symbol"] == "BTCUSDT"
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_ohlcv_happy_path_normalizes_candles():
    """OHLCV fetch should normalize Binance kline arrays."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return httpx.Response(200, json=[_kline_payload()])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_ohlcv("ETH", "1h", 1)

    assert len(records) == 1
    assert records[0].asset == "ETH"
    assert records[0].exchange == "binance"
    assert records[0].interval == "1h"
    assert records[0].ts == datetime.fromtimestamp(1715779020000 / 1000, tz=timezone.utc)
    assert records[0].open == Decimal("3000.00")
    assert records[0].high == Decimal("3100.00")
    assert records[0].low == Decimal("2990.00")
    assert records[0].close == Decimal("3050.00")
    assert records[0].volume == Decimal("12.5")
    assert records[0].quote_volume == Decimal("38125.00")
    assert observed_requests[0].url.path == "/api/v3/klines"
    assert observed_requests[0].url.params["symbol"] == "ETHUSDT"
    assert observed_requests[0].url.params["interval"] == "1h"
    assert observed_requests[0].url.params["limit"] == "1"
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_all_stage_a_symbols_are_supported_for_tickers():
    """All configured Stage A assets should map to Binance public ticker symbols."""
    observed_paths: list[str] = []
    observed_symbols: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        symbol = request.url.params["symbol"]
        observed_symbols.append(symbol)
        return httpx.Response(200, json=_ticker_payload(symbol))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshots = await BinanceCollector(client=client).fetch_tickers(
            ["BTC", "ETH", "SOL", "SUI", "TON", "UNI"]
        )

    assert [snapshot.asset for snapshot in snapshots] == [
        "BTC",
        "ETH",
        "SOL",
        "SUI",
        "TON",
        "UNI",
    ]
    assert set(observed_paths) == {"/api/v3/ticker/24hr"}
    assert observed_symbols == [
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "SUIUSDT",
        "TONUSDT",
        "UNIUSDT",
    ]


@pytest.mark.asyncio
async def test_unsupported_symbol_returns_empty_and_records_failure():
    """Unsupported symbols should be isolated as source failures."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_unexpected_request)) as client:
        snapshots = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_tickers(["XRP"])

    assert snapshots == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "not supported" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_tickers_http_500_returns_empty_list():
    """HTTP 500 should be recorded as source failure without raising outward."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"msg": "server error"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshots = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_tickers(["BTC"])

    assert snapshots == []
    assert len(recorder.failures) == 1
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_tickers_timeout_returns_empty_list():
    """Timeout should be recorded as source failure without retrying."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshots = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_tickers(["BTC"])

    assert snapshots == []
    assert len(recorder.failures) == 1
    assert "timed out" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_ohlcv_empty_response_returns_empty_list():
    """Empty Binance kline responses should produce no OHLCV records."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_ohlcv("BTC", "4h")

    assert records == []
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_ohlcv_invalid_interval_returns_empty_list():
    """Unsupported intervals should be rejected before making HTTP requests."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_unexpected_request)) as client:
        records = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_ohlcv("BTC", "15m")

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "interval" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_ohlcv_http_500_returns_empty_list():
    """Kline HTTP failures should be recorded and bounded."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"msg": "server error"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BinanceCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_ohlcv("BTC", "1d")

    assert records == []
    assert len(recorder.failures) == 1
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_tickers_uses_only_public_spot_market_paths():
    """Ticker fetches should not use private or derivatives endpoints."""
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        return httpx.Response(200, json=_ticker_payload(request.url.params["symbol"]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        snapshots = await BinanceCollector(client=client).fetch_tickers(["BTC", "ETH"])

    assert len(snapshots) == 2
    assert set(observed_paths) == {"/api/v3/ticker/24hr"}
    assert all(
        "funding" not in path
        and "account" not in path
        and "order" not in path
        and "margin" not in path
        for path in observed_paths
    )


def test_normalize_ticker_payload_rejects_malformed_static_payload():
    """Static ticker normalization should reject missing required price fields."""
    with pytest.raises(MarketDataPayloadError, match="lastPrice"):
        BinanceCollector().normalize_ticker_payload({"symbol": "BTCUSDT"})


def _ticker_payload(symbol: str) -> dict[str, str]:
    return {
        "symbol": symbol,
        "lastPrice": "67123.45",
        "quoteVolume": "123456789.12",
        "priceChangePercent": "2.345",
    }


def _kline_payload() -> list[object]:
    return [
        1715775420000,
        "3000.00",
        "3100.00",
        "2990.00",
        "3050.00",
        "12.5",
        1715779020000,
        "38125.00",
        10,
        "7.5",
        "22875.00",
        "0",
    ]


def _unexpected_request(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"Unexpected Binance request: {request.url}")
