# Duzman Architecture

Текущее состояние архитектуры по дням реализации. Обновляется в конце каждой задачи.

## Состояние на конец дня 6

### Структура

src-layout, editable install через .venv/bin/python -m pip install -e .

### Модули src/duzman/

- collectors/ — публичные коллекторы Binance и CoinGecko (только спот-цены и OHLCV)
- db/ — SQLAlchemy 2.0 модели, repository pattern, Alembic миграции, 14 таблиц включая liquidation_heatmap
- api/ — FastAPI app factory create_app(), read-only роуты /api/market-data/*
- scheduler/ — APScheduler с CronTrigger XX:17 UTC для market data и XX:23 UTC для indicators; jobs зарегистрированы, не запускаются автоматически
- runtime/ — one-shot entrypoints (run_market_data_collection_once, verify_local_database, verify_read_only_api)
- settings.py, main.py

### Коллекторы

- BinanceCollector — публичные Binance spot endpoints /api/v3/ticker/24hr и /api/v3/klines для 6 активов Stage A
- AlternativeMeCollector — публичный Alternative.me Fear & Greed endpoint /fng/?limit=1; пишет fear_greed_index через GlobalMetricRepository
- BybitCollector — публичные derivatives endpoints Bybit v5 для funding rate, open interest и long/short ratio; не собирает спот-цены
- CoinGeckoCollector — fallback для цен и BTC dominance (последнее ещё не подключено)
- CoinGeckoGlobalCollector — публичный CoinGecko Global endpoint /api/v3/global для BTC dominance; пишет через GlobalMetricRepository
- CoinGlassCollector — публичные CoinGlass endpoints для hourly liquidations по 6 активам и simplified heatmap BTC/ETH; требует operator-provided API key
- FarsideCollector — публичный HTML-парсер Farside Investors для дневных BTC/ETH ETF net flows; пишет через ETFFlowRepository, без live API в тестах
- OKXCollector — публичные derivatives endpoints OKX v5 для funding rate, open interest и long/short ratio; не собирает спот-цены

### Indicators

- RSI — pandas-ta RSI по close, default period=14
- Stochastic — pandas-ta Stochastic по high/low/close, k=14, d=3, smoothing=3
- Realized Volatility 24h — annualized volatility по 1h close returns, минимум 25 свечей
- Premium/Discount — (perp_price - spot_price) / spot_price * 100

### Pattern Engine — Config Layer

- `src/duzman/patterns/` — Pydantic v2 models and `load_patterns()` for `config/patterns.yaml`; validates known metrics, operators, Stage A assets, unique names, and nested all/any condition groups.
- `config/patterns.yaml` — 10 deterministic Appendix A v1.4 pattern definitions; A.6/A.7 use `per_asset_thresholds` for BTC/ETH ETF flow thresholds.

### Pattern Engine — Snapshot Layer

- `src/duzman/patterns/snapshot.py` — async `build_snapshot(session, assets, now)` builds immutable `MetricsSnapshot` and per-asset `AssetMetrics` from `KNOWN_METRICS`; global metrics are kept separate from asset values.
- `src/duzman/db/repositories/snapshot_repository.py` — read repository for snapshot source rows; direct mappings cover RSI, Stochastic, volatility, premium/discount, price changes, liquidations, Fear & Greed, and BTC dominance.
- Derived calculations are computed at snapshot time: funding average/dislocation, 24h OI change, ETF streak, ETF cumulative five-day flow in USD, price-vs-BTC seven-day change, and BTC dominance seven-day percentage-point change.
- Missing, stale, inapplicable, or failed metric calculations degrade to `None`; per-derived failures log `derived_metric_failed`, and successful builds log `snapshot_built` with asset and populated-metric counts.

### Pattern Engine — Evaluation Layer

- `src/duzman/patterns/evaluation.py` — pure sync `evaluate_patterns(patterns, snapshot)` returns immutable `PatternMatch` rows ordered by `(pattern_name, asset)`; it does not use the database, scheduler, cooldowns, or AlertGate.
- `PatternMatch.conditions_snapshot` stores only metrics referenced by the matched pattern conditions, including global metrics when used; `evaluated_at` is copied from `MetricsSnapshot.built_at`.
- `None` metric values block matches, while missing per-asset thresholds log `pattern_misconfigured` and make the condition false.
- Condition groups support recursive `all`/`any` semantics, and per-asset thresholds take precedence over scalar condition values when present.
- Per-pattern evaluation failures log `pattern_evaluation_failed` and do not stop evaluation of other patterns or assets.

### Pattern Engine — AlertGate Layer

- `src/duzman/patterns/alert_gate.py` — pure async decision layer between evaluation and persistence; applies cooldown, daily hard cap, hourly hard cap, and soft cap in TZ v1.6 order, with CRITICAL bypassing only the soft cap.
- `src/duzman/db/repositories/pattern_trigger_repository.py` — persists day-6 pattern trigger rows and reads ALLOW counters from `pattern_triggers.conditions_snapshot.gate_decision`; callers own transaction commits.
- `src/duzman/scheduler/hourly_tick.py` — hourly Pattern Engine integration; builds one tick timestamp, evaluates patterns, runs one transaction per `(AlertGate.evaluate + insert_trigger)`, and dispatches only ALLOW matches after all gate transactions are committed.
- Day 6 does not write `alerts_sent`; `alert_sent` remains false, and the AlertGate decision is stored in `conditions_snapshot.gate_decision` until day-7 dispatch persistence integration.
- Alembic migration `b009e25bfab4` creates `pattern_triggers` for persisted day-6 Pattern Engine matches and gate decisions.

### Day 6 Implemented Baseline

- Pattern evaluation pipeline: `src/duzman/patterns/evaluation.py`
- AlertGate decision layer: `src/duzman/patterns/alert_gate.py`
- Pattern trigger repository: `src/duzman/db/repositories/pattern_trigger_repository.py`
- Hourly Pattern Engine tick: `src/duzman/scheduler/hourly_tick.py`
- `pattern_triggers` schema migration: Alembic revision `b009e25bfab4`

#### Known Limitations

Two-phase read-then-write in evaluate (`count_allow_in_window`/`cooldown_hit`, then `insert_trigger`) is not atomic. This is acceptable under the single-threaded hourly scheduler: one tick at a time, transaction per match commits before the next match. Revisit if concurrency is added: options are PostgreSQL advisory locks per `(asset, pattern_id)`, or `SELECT FOR UPDATE` on a per-pattern lock row.

### Scheduler

- indicator_jobs.py — hourly deterministic indicator collection at XX:23 UTC; reads Binance OHLCV/tickers and Bybit mark prices, then persists indicators
- coingecko_global_hourly — hourly BTC dominance collection at XX:17 UTC; appends global_metrics rows via GlobalMetricRepository
- coinglass_hourly — hourly CoinGlass liquidation and heatmap collection at XX:18 UTC; uses LiquidationRepository and HeatmapRepository
- etf_flows_daily — daily Farside ETF flow collection at 02:17 UTC; job registered in runtime scheduler and not started automatically
- fear_greed_daily — daily Alternative.me Fear & Greed collection at 02:17 UTC; job registered independently and not started automatically

### Read-only API

- GET /api/market-data/prices/latest — последние цены из price_snapshots
- GET /api/market-data/source-health — статус источников
- GET /api/market-data/ingestion-status — общий статус сбора + ingestion_health_summary
- GET /api/market-data/ingestion-alerts — детерминированные алерты по ingestion

### Тесты

pytest, async, моки httpx. Все 268 тестов зелёные на дне 6. Никаких живых API.

### Что НЕ реализовано на конец дня 6

- Telegram-отправка алертов
- AI-объяснения через Anthropic API
- Дашборд: FastAPI `/api/v1/` полностью, HTML + Plotly.js
- Caddy + HTTPS
- Deploy script в `/opt/duzman`
- Daily backup в Telegram + weekly OneDrive
- Retention job
- Daily digest
