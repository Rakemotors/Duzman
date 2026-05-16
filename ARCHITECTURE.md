# Duzman Architecture

Текущее состояние архитектуры по дням реализации. Обновляется в конце каждой задачи.

## Состояние на конец дня 3

### Структура

src-layout, editable install через .venv/bin/python -m pip install -e .

### Модули src/duzman/

- collectors/ — публичные коллекторы Binance и CoinGecko (только спот-цены и OHLCV)
- db/ — SQLAlchemy 2.0 модели, repository pattern, Alembic миграции, 13 таблиц по Приложению Б ТЗ
- api/ — FastAPI app factory create_app(), read-only роуты /api/market-data/*
- scheduler/ — APScheduler с CronTrigger XX:17 UTC для market data и XX:23 UTC для indicators; jobs зарегистрированы, не запускаются автоматически
- runtime/ — one-shot entrypoints (run_market_data_collection_once, verify_local_database, verify_read_only_api)
- settings.py, main.py

### Коллекторы

- BinanceCollector — публичные Binance spot endpoints /api/v3/ticker/24hr и /api/v3/klines для 6 активов Stage A
- BybitCollector — публичные derivatives endpoints Bybit v5 для funding rate, open interest и long/short ratio; не собирает спот-цены
- CoinGeckoCollector — fallback для цен и BTC dominance (последнее ещё не подключено)
- OKXCollector — публичные derivatives endpoints OKX v5 для funding rate, open interest и long/short ratio; не собирает спот-цены

### Indicators

- RSI — pandas-ta RSI по close, default period=14
- Stochastic — pandas-ta Stochastic по high/low/close, k=14, d=3, smoothing=3
- Realized Volatility 24h — annualized volatility по 1h close returns, минимум 25 свечей
- Premium/Discount — (perp_price - spot_price) / spot_price * 100

### Scheduler

- indicator_jobs.py — hourly deterministic indicator collection at XX:23 UTC; reads Binance OHLCV/tickers and Bybit mark prices, then persists indicators

### Read-only API

- GET /api/market-data/prices/latest — последние цены из price_snapshots
- GET /api/market-data/source-health — статус источников
- GET /api/market-data/ingestion-status — общий статус сбора + ingestion_health_summary
- GET /api/market-data/ingestion-alerts — детерминированные алерты по ingestion

### Тесты

pytest, async, моки httpx. Все 92 теста зелёные на дне 3. Никаких живых API.

### Что НЕ реализовано на конец дня 3

- Bybit и OKX коллекторы (день 4)
- Индикаторы RSI, Stochastic, Volatility (день 4)
- Premium/Discount (день 4)
- ETF flows, CoinGlass, BTC dominance, Fear&Greed (день 5)
- Pattern Engine (день 6)
- Telegram, AI-объяснения (день 7)
- Дашборд, /api/v1/ роуты (день 8)
- Production deployment, бэкапы (день 9)
