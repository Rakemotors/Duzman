# Local Development Setup

This repository uses a project-local Python virtual environment for development and test commands. Do not install Duzman Python dependencies globally.

## Create the virtual environment

From the repository root:

```bash
python3 -m venv .venv
```

The `.venv/` directory is ignored by git.

## Install dependencies

Upgrade pip inside the virtual environment:

```bash
.venv/bin/python -m pip install --upgrade pip
```

Install project dependencies into `.venv` only:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Do not use `sudo`, `apt`, global `pip install`, `pip install --user`, or shell profile changes for this setup.

## Run tests

Run pytest through the virtual environment:

```bash
.venv/bin/python -m pytest
```

Current status: pytest is runnable from `.venv` and the offline test suite passes.

Collector tests use static Binance and CoinGecko sample payloads. They do not call live APIs, require API keys, access trading endpoints, or place orders.

HTTP/fetcher tests use mocked `httpx` transports. They do not call live Binance or CoinGecko APIs.

## Database configuration

Duzman does not provide a default database password or fallback connection string in code. Runtime commands that open database sessions require `DATABASE_URL` to be configured by the Operator.

The offline test suite does not require `DATABASE_URL`, `.env`, or a live PostgreSQL connection.

## Run Alembic checks

Show migration history:

```bash
.venv/bin/alembic history
```

Current status: this succeeds and shows the initial schema migration:

```text
<base> -> b009e25bfab4 (head), initial schema
```

Check the current database revision:

```bash
.venv/bin/alembic current
```

Current status: this command was attempted and fails before connecting to PostgreSQL because no database URL is configured for Alembic in the current shell. The observed failure is:

```text
KeyError: 'url'
```

Do not create or edit `.env` as part of routine test setup. A future task should define a safe local database configuration pattern for development and Alembic checks.

## Known current gaps

- Alembic `current` needs a safe local database configuration before it can report a live database revision.
- The current tests validate imports, SQLAlchemy metadata, Alembic file presence, and ORM/migration schema consistency without connecting to PostgreSQL.
- Binance and CoinGecko collectors currently provide public-data request definitions and payload normalization only.
- The ingestion service persists supplied/static payloads to `price_snapshots` in tests without live API calls.
- The scheduler helper registers an hourly ingestion job definition but does not start production scheduling automatically.
- Public HTTP fetchers exist for explicit public market-data requests, with source health tracking for status, latency, and bounded error messages.
- The market data collection job wires public fetchers, `price_snapshots` persistence, and source health checks in offline tests with fake fetchers.
- Tests do not apply live database migrations or start a production scheduler.
- The runtime scheduler entrypoint can build an APScheduler instance for the market data job, but it does not auto-start, install systemd, add Docker, add Redis/Celery/queues, or apply migrations.
