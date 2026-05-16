# Duzman

Персональный crypto metrics monitor. Этап А.

См. техническое задание (Duzman_TZ_v1.2).

## Local development

Use a project-local virtual environment only. See `docs/LOCAL_DEV_SETUP.md` for setup, dependency installation, pytest, and Alembic check commands.

Runtime commands use the local `duzman` package from `src/`; install the project into `.venv` with `.venv/bin/python -m pip install -e .` before running `python -m duzman...` commands.

## Stage A public market data

The current Day 2 collector foundation supports Binance and CoinGecko public market data normalization for offline-tested Stage A assets. It does not require API keys, does not use account or order endpoints, and does not place trades.

`price_snapshots` persistence is available through a repository and ingestion service for supplied public payloads. The scheduler foundation can register an hourly ingestion job at `XX:17 UTC`, but it does not start a production scheduler or call live APIs on import.

Public Binance and CoinGecko fetchers use a small GET-only HTTP abstraction and remain public-data only: no API keys, private endpoints, account endpoints, order endpoints, or trading actions. Source health checks can record source status, latency, and bounded error messages for explicit fetch attempts.

An explicit market data collection job wires public fetches, price snapshot persistence, and source health tracking for BTC/ETH. It is callable by APScheduler registration, but no scheduler starts automatically.

The runtime module `duzman.runtime.market_data_scheduler` can build a scheduler with the hourly market data job registered. It does not install a service, start on import, apply migrations, require API keys, or place orders.

Structured logging is available for the public HTTP client, source health tracking, collection job, and explicit scheduler runtime. Logging uses safe event-style messages, avoids raw payload bodies and query parameters, and is configured only when a runtime entrypoint is explicitly invoked.

Run one manual collection cycle with:

```bash
.venv/bin/python -m duzman.runtime.run_market_data_collection_once
```

The command runs exactly one public Binance/CoinGecko collection cycle, writes `price_snapshots` and source health checks through the existing services, configures structured logging explicitly, and exits. It does not start APScheduler, install services, run migrations, require exchange API keys, or place orders.

Runtime database access is supplied through `DATABASE_URL`. Use placeholder-only examples in docs and never commit real passwords, paste secrets into Codex/ChatGPT logs, or store database passwords in shell profiles. Live migrations are a separate controlled step and are not run by the one-shot command.

For local database preparation, follow the operator-controlled checklist in `docs/LOCAL_DEV_SETUP.md`. It documents placeholder-only `DATABASE_URL` usage, keeps secrets out of `.env` and shell profiles, and treats live migrations as a separately approved step.

## Read-only API

The FastAPI app factory `duzman.api.create_app()` registers read-only market data routes:

- `GET /api/market-data/prices/latest`
- `GET /api/market-data/source-health`
- `GET /api/market-data/ingestion-status`

These routes read already persisted public market data only. They do not start APScheduler, run collection, call live exchange APIs, run migrations, place orders, or access private exchange/account endpoints.

Verify route registration offline with:

```bash
.venv/bin/python -m duzman.runtime.verify_read_only_api
```

Expected output: `READ_ONLY_API_RUNTIME_CHECK_OK`.
