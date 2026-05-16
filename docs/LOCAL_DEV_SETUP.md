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

Install the local `src/` package into `.venv` in editable mode so runtime commands can import `duzman` outside pytest:

```bash
.venv/bin/python -m pip install -e .
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

For a single manual runtime command, provide `DATABASE_URL` only for that command invocation. Use the real password only in an Operator-controlled shell, and do not paste it into Codex, ChatGPT, issue trackers, docs, or logs.

Placeholder example:

```bash
DATABASE_URL="postgresql+psycopg://duzman_user:REPLACE_WITH_PASSWORD@localhost:5432/duzman" \
.venv/bin/python -m duzman.runtime.run_market_data_collection_once
```

This example is intentionally fake. Replace `REPLACE_WITH_PASSWORD` only in a private Operator-controlled context.

Do not:

- put database passwords in `~/.bashrc`, `~/.profile`, `~/.zshrc`, `/etc/environment`, or other global shell profiles;
- commit `.env` or any file containing real secrets;
- print environment variables with `env` or `printenv`;
- paste real database URLs, passwords, API keys, tokens, seed phrases, or wallet private keys into Codex/ChatGPT logs;
- add exchange private API keys, account endpoints, order endpoints, or trading credentials for Stage A.

If runtime database configuration is missing, the one-shot command should fail safely before opening a database session and log a controlled failure. It does not need exchange API keys because the current collectors use public market-data endpoints only.

## Operator-controlled local database bootstrap

This section documents a safe local PostgreSQL bootstrap procedure for a human Operator to run later. It is not executed by Codex during documentation, test, or review tasks.

Use `DATABASE_URL` only as an inline prefix for the one command that needs it. Do not store it in `.env`, shell profiles, `/etc/environment`, shared notes, issue trackers, docs, logs, or chat transcripts.

Every command below uses placeholder values only. Replace placeholders only in a private Operator-controlled shell:

```bash
DATABASE_URL="postgresql+psycopg://duzman_user:REPLACE_WITH_PASSWORD@localhost:5432/duzman" \
.venv/bin/python -m duzman.runtime.run_market_data_collection_once
```

Safe operator sequence for a later explicitly approved local bootstrap:

1. Confirm the repository is clean with `git status`.
2. Confirm tests and offline checks still pass without any database secret:
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/alembic heads`
   - `.venv/bin/python -m duzman.runtime.verify_read_only_api`
3. Prepare the local PostgreSQL database outside Codex, without pasting credentials into Codex, ChatGPT, docs, logs, or issue trackers.
4. Apply Alembic migrations only after separate explicit human approval for a live database migration step. Use the same one-command inline `DATABASE_URL` pattern and do not ask Codex to run this command without that separate approval.
5. Run one manual public market-data collection cycle with `DATABASE_URL` provided only for that command invocation.
6. Verify read-only API route registration offline with `.venv/bin/python -m duzman.runtime.verify_read_only_api`, or query the read-only routes only through an explicitly approved local app runner.
7. Avoid printing secrets. Do not use `env`, `printenv`, shell profile exports, or committed config files to inspect or persist `DATABASE_URL`.

The one-shot collection command does not create databases, run migrations, start APScheduler, install services, start Docker, bind public ports, or place trades. It expects the Operator to provide an already prepared database connection for the single command invocation.

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

Do not create or edit `.env` as part of routine test setup. Live Alembic migration commands require separate explicit human approval and an Operator-controlled inline `DATABASE_URL`.

## Run one manual collection cycle

After the Operator has configured database access outside this test workflow, run exactly one public market-data collection cycle with:

```bash
.venv/bin/python -m duzman.runtime.run_market_data_collection_once
```

Optional log level:

```bash
.venv/bin/python -m duzman.runtime.run_market_data_collection_once --log-level INFO
```

The command configures structured logging only when explicitly invoked. Logs use safe event names and key/value fields, avoid raw payload bodies and query parameters, and do not print environment variables or secrets.

The command does not start APScheduler, install systemd, add Docker, add Redis/Celery/queues, run database migrations, require exchange API keys, access private account/order endpoints, or place trades.

Live database migrations are a separate controlled operation. Do not run `alembic upgrade` against a live database unless that is explicitly approved as a separate task.

## Inspect read-only API routes

The FastAPI app factory is available as `duzman.api.create_app()`. It registers read-only routes for already persisted public market data:

- `GET /api/market-data/prices/latest`
- `GET /api/market-data/source-health`
- `GET /api/market-data/ingestion-status`

Example placeholder requests:

```text
GET /api/market-data/prices/latest?symbol=BTC&source=binance&limit=20
GET /api/market-data/source-health?source=binance
GET /api/market-data/ingestion-status
```

These routes do not start APScheduler, trigger collection, call live Binance/CoinGecko APIs, run database migrations, require exchange API keys, access private account/order endpoints, or place trades. They require an application database session at runtime and are tested offline with local test databases.

Verify read-only API app creation and route registration offline:

```bash
.venv/bin/python -m duzman.runtime.verify_read_only_api
```

Expected output:

```text
READ_ONLY_API_RUNTIME_CHECK_OK
```

This smoke check instantiates the FastAPI app and verifies route registration only. It does not require `DATABASE_URL`, start APScheduler, call Binance/CoinGecko, run migrations, bind a public port, or place trades.

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
- Structured logging exists for the public HTTP client, source health tracking, collection job, and explicit runtime entrypoint. Logs use safe event names and key/value fields, avoid raw payload bodies and query parameters, and do not require API keys or any secret configuration.
- The one-shot collection command can run one explicit collection cycle, but it requires safe runtime database configuration and does not apply migrations automatically.
- The read-only API routes expose persisted public market data and source health only; they do not trigger collection or scheduler startup.
