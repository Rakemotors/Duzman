# Duzman

Персональный crypto metrics monitor. Этап А.

См. техническое задание (Duzman_TZ_v1.2).

## Local development

Use a project-local virtual environment only. See `docs/LOCAL_DEV_SETUP.md` for setup, dependency installation, pytest, and Alembic check commands.

## Stage A public market data

The current Day 2 collector foundation supports Binance and CoinGecko public market data normalization for offline-tested Stage A assets. It does not require API keys, does not use account or order endpoints, and does not place trades.

`price_snapshots` persistence is available through a repository and ingestion service for supplied public payloads. The scheduler foundation can register an hourly ingestion job at `XX:17 UTC`, but it does not start a production scheduler or call live APIs on import.

Public Binance and CoinGecko fetchers use a small GET-only HTTP abstraction and remain public-data only: no API keys, private endpoints, account endpoints, order endpoints, or trading actions. Source health checks can record source status, latency, and bounded error messages for explicit fetch attempts.

An explicit market data collection job wires public fetches, price snapshot persistence, and source health tracking for BTC/ETH. It is callable by APScheduler registration, but no scheduler starts automatically.
