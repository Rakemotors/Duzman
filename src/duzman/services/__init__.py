"""Application services for Duzman Stage A."""

from duzman.services.market_data import MarketDataService
from duzman.services.market_data_collection_job import (
    DEFAULT_BINANCE_SYMBOLS,
    DEFAULT_COINGECKO_COIN_IDS,
    MarketDataCollectionJob,
    MarketDataCollectionResult,
    run_public_market_data_ingestion_job,
)
from duzman.services.market_data_fetchers import PublicMarketDataFetcher
from duzman.services.market_data_ingestion import (
    MarketDataIngestionResult,
    MarketDataIngestionService,
)
from duzman.services.ingestion_health_alerts import (
    DEFAULT_PRICE_SNAPSHOT_FRESHNESS_THRESHOLD,
    DEFAULT_SOURCE_HEALTH_FRESHNESS_THRESHOLD,
    IngestionHealthAlert,
    IngestionHealthSummary,
    evaluate_ingestion_health_alerts,
    summarize_ingestion_health,
)
from duzman.services.public_http_client import (
    PublicHttpClient,
    PublicHttpClientError,
    PublicHttpJsonError,
    PublicHttpNetworkError,
    PublicHttpStatusError,
    PublicHttpTimeoutError,
)
from duzman.services.source_health_tracking import (
    SourceHealthTrackingResult,
    SourceHealthTrackingService,
)

__all__ = [
    "MarketDataIngestionResult",
    "MarketDataIngestionService",
    "MarketDataService",
    "DEFAULT_BINANCE_SYMBOLS",
    "DEFAULT_COINGECKO_COIN_IDS",
    "MarketDataCollectionJob",
    "MarketDataCollectionResult",
    "DEFAULT_PRICE_SNAPSHOT_FRESHNESS_THRESHOLD",
    "DEFAULT_SOURCE_HEALTH_FRESHNESS_THRESHOLD",
    "IngestionHealthAlert",
    "IngestionHealthSummary",
    "evaluate_ingestion_health_alerts",
    "summarize_ingestion_health",
    "PublicHttpClient",
    "PublicHttpClientError",
    "PublicHttpJsonError",
    "PublicHttpNetworkError",
    "PublicHttpStatusError",
    "PublicHttpTimeoutError",
    "PublicMarketDataFetcher",
    "run_public_market_data_ingestion_job",
    "SourceHealthTrackingResult",
    "SourceHealthTrackingService",
]
