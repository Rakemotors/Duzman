# Duzman Architecture

Based on: Техническое задание v1.10 от 25 мая 2026 (docs/TZ.md)

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

### Stage A Asset Seed

`src/duzman/assets.py` is the canonical source of truth for Stage A asset
symbols. Adding a Stage A asset means updating this module and adding a new
idempotent seed migration in the same PR.

Alembic revision `e6f4a9b2c1d3` seeds canonical Stage A assets and is
idempotent via PostgreSQL `ON CONFLICT DO NOTHING`. The same FK on
`assets.symbol` is shared by `indicators`, `price_snapshots`,
`funding_rates`, `open_interest`, `long_short_ratio`, `liquidations`,
`liquidation_heatmap`, and `pattern_triggers`, so this seed unblocks all of
them simultaneously.

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

### Day 7 Telegram Delivery

- `src/duzman/telegram/` implements a single-chat Telegram MVP through `python-telegram-bot==21.11.1` long polling; imports are side-effect free and the worker starts only through `build_telegram_worker` / `start_telegram_background_task`.
- `TelegramAlertPoller` reads AlertGate `ALLOW` rows from `pattern_triggers`, sends a bounded startup digest, then polls for undelivered rows every `TELEGRAM_ALERT_POLL_INTERVAL_SECONDS`.
- `TelegramAlertSender` sends through an injected client, retries transient failures three times, and records `sent`, `failed`, or `snoozed` rows in `alert_deliveries`; sent rows persist the Telegram base `message_id` for day-8 reply delivery.
- `telegram_channel_state` stores global delivery state only (`enabled`, `muted`, `snooze_until`); Telegram token and chat id stay in `.env` / settings and are never persisted.
- Supported commands: `/start`, `/help`, `/status`, `/alerts`, `/mute`, `/unmute`, `/snooze`.
- Alembic migration `d7e1f2a3b4c5` creates `alert_deliveries` and `telegram_channel_state`.

### Day 8 AI Explanations

- `src/duzman/ai/` implements the optional Anthropic explanation layer: API client wrapper, prompt builder, budget/cache helpers, task service, and sequential background worker.
- `alert_explanations` stores one idempotent explanation task per `pattern_trigger_id`, with terminal statuses for completed, reused cache, cost-cap skip, disabled skip, missing base message id, failed, and failed stale.
- Existing failed, failed stale, and cost-cap skipped explanation rows may be reset in place to `pending` by `create_pending_explanation()` with the current `alert_delivery_id` and prompt cache metadata; completed, reused cache, disabled, missing-base-message, pending, and running rows remain non-retryable to avoid duplicate spend or duplicate replies.
- Cost caps count only terminal Anthropic-attempt statuses (`completed`, `failed`, `failed_stale`) using `completed_at` with `created_at` fallback, so a claimed `running` row cannot block itself and same-row retries count in the window where they finish.
- Telegram delivery remains the source of ordering: the base alert is sent first, its `telegram_message_id` is stored in `alert_deliveries`, and explanations are sent later as Telegram replies.
- The layer is feature-flagged by `AI_EXPLANATIONS_ENABLED`; missing `ANTHROPIC_API_KEY`, API failures, cost caps, or missing base message ids do not block normal AlertGate or Telegram delivery.
- Settings reject `claude-opus-*` model names for the Day 8 MVP, keeping the explanation layer on Sonnet-class models.
- Prompt context is normalized and bounded, excludes raw payloads and credentials, and the Anthropic key is read only from Settings.
- Runtime wiring: `src/duzman/ai/app.py` exposes `build_components_from_settings()` which assembles async engine, session factory, AnthropicClient, Telegram sender, ExplanationService, and ExplanationWorker. Worker is launched via `src/duzman/runtime/run_ai_explanation_worker.py` supporting both `run_forever` (daemon) and `--run-once` modes. Async DB URL is derived from `settings.database_url` at startup (`postgresql://` → `postgresql+asyncpg://`); the `.env` `DATABASE_URL` stays in sync form for existing sync code.
- Alembic migration `8f3a2c1b9d6e` creates `alert_explanations`; migration `9b7c6d5e4f3a` adds `alert_deliveries.telegram_message_id`.

### Phase 2 Dispatch Contract

- `src/duzman/dispatch/contract.py` defines the pure dispatch domain boundary:
  immutable `DispatchEvent` and `DispatchResult` dataclasses, the `Dispatcher`
  protocol, and `build_dispatch_event()` validation from primitive values only.
- The contract has no database, scheduler, AlertGate, Pattern Engine, Telegram,
  Anthropic, market-data, network, or runtime entrypoint dependency.
- `pattern_triggers.id` is the dispatch idempotency anchor and is represented in
  Python domain code as `pattern_trigger_id`.
- Historical DB naming drift: `alert_deliveries.alert_id` semantically maps to
  `pattern_triggers.id`. New Python domain code should use
  `pattern_trigger_id` while treating that DB column as the persisted trigger
  reference.

### Phase 2 Telegram Base Sender

- `src/duzman/dispatch/telegram/` defines the inert Spec 2 Telegram base sender
  boundary: deterministic MarkdownV2 formatting, an injectable async HTTP
  client, bounded send results, and a `TelegramBaseSender` orchestrator.
- The sender uses `DispatchEvent` from the Spec 1 contract but is not wired to
  scheduler/runtime, AlertGate, Pattern Engine, database persistence, AI
  explanations, or production deployment in Spec 2.
- Telegram configuration is represented in `src/duzman/settings.py` by
  `telegram_enabled`, `telegram_bot_token`, `telegram_chat_id`, and
  `telegram_timeout_ms`; Telegram dispatch remains disabled by default and
  future Spec 5 runtime wiring must opt in explicitly.
- Tests for this layer use fake HTTP transports only. Real Telegram API calls,
  real bot tokens, and real chat ids are out of scope for Spec 2.

### Phase 2 Dispatch Persistence

- `src/duzman/dispatch/persistence/` defines the inert Spec 3 persistence
  boundary for recording dispatch delivery outcomes in the existing
  `alert_deliveries` table.
- `DispatchDeliveryRepository` is session-scoped: callers inject an
  `AsyncSession` and retain ownership of transactions, session lifecycle, and
  async engine disposal. The repository does not create engines or commit.
- The repository reuses the existing `src/duzman/db/models.py::AlertDelivery`
  ORM model and adds no migration. The existing day-7
  `src/duzman/db/repositories/alert_deliveries.py::AlertDeliveryRepository`
  remains unchanged for legacy Telegram runtime paths.
- Domain code uses `pattern_trigger_id`; the repository maps that value to the
  historical DB column `alert_deliveries.alert_id`. Idempotency is enforced at
  `(alert_id, channel)` through dialect-aware `ON CONFLICT DO NOTHING` inserts.
- Spec 3 is not wired to scheduler/runtime, AlertGate, Pattern Engine, Telegram
  sending, database session composition, or AI explanations. Future Spec 5
  orchestration will compose this persistence boundary with Spec 1 and Spec 2.

### Day 8 Smoke Harness

- `src/duzman/runtime/verify_telegram_base.py` is the B0 dev-only smoke entrypoint. It inserts one synthetic `smoke_b0` AlertGate trigger for BTC, runs Telegram base delivery with AI disabled, and verifies that `alert_deliveries.telegram_message_id` is persisted.
- `src/duzman/runtime/run_ai_explanation_smoke.py` is the B1 dev-only smoke entrypoint. It takes a B0 trigger id, validates `pattern_name == "smoke_b0"`, creates or reuses a pending explanation task, runs one AI worker cycle, and can roll back the smoke chain with `--rollback`.
- These scripts are not registered in APScheduler and are not called by the production scheduler. They are manual pre-rollout verification commands for Telegram base delivery and AI explanation delivery.
- Full operator contract, exit codes, required environment variables, database preconditions, and rollback semantics are documented in `docs/specs/day8_smoke_harness.md`.

### Codex Issue Dispatcher Research

- `docs/research/codex_issue_dispatcher.md` records the Issue #31 Level 2 automation research outcome. Full automation from `codex-ready` GitHub Issues to Codex CLI runs and PR creation is postponed until explicit Operator approval gates, runner safety, and audit controls are accepted.
- Current default remains the Level 1 manual workflow: approved Issue, Operator-provided prompt, Codex/Claude Code execution, PR review, and Operator merge. No watcher, GitHub Action, systemd unit, or product runtime component exists for the dispatcher.

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
- pattern_tick_hourly — hourly Pattern Engine tick at XX:33 UTC; persists AlertGate decisions to pattern_triggers with dispatch disabled
- etf_flows_daily — daily Farside ETF flow collection at 02:17 UTC; job registered in runtime scheduler and not started automatically
- fear_greed_daily — daily Alternative.me Fear & Greed collection at 02:17 UTC; job registered independently and not started automatically

### Read-only API

- GET /api/market-data/prices/latest — latest prices from price_snapshots
- GET /api/market-data/source-health — source health status
- GET /api/market-data/ingestion-status — ingestion summary plus ingestion_health_summary
- GET /api/market-data/ingestion-alerts — deterministic ingestion alerts

All `/api/market-data/*` routes are protected at router level by the
`X-API-Key` header. `DUZMAN_API_KEY` is the source of truth, and empty or
missing configuration fails closed during `create_app()` before protected
routes are served. Missing, empty, or incorrect request keys return 401 with
`WWW-Authenticate: ApiKey realm="duzman"`.

`/health` remains open because it belongs to the separate health server
(`duzman.runtime.run_health_server`), not the main FastAPI API app. The
health payload includes liveness status, package version, UTC timestamp, and a
best-effort `build_sha`. The build SHA file resolves independently of process
cwd: `DUZMAN_BUILD_SHA_PATH` can override the file path, otherwise the default
is package-anchored as `<repo>/BUILD_SHA` from the installed `duzman` package
location. If no file value is available, `/health` falls back to
`DUZMAN_BUILD_SHA`, then `unknown`. The
`/api/market-data/ingestion-status` route is intentionally protected because
it exposes operational telemetry including assets seen, sources seen,
timestamps, counts, health state, and alerts.

### Тесты

pytest, async, моки httpx. Все 268 тестов зелёные на дне 6. Никаких живых API.

### Day 9 — Deployment and systemd

Day 9 deployment is documented in `deploy/README.md` and implemented by
`deploy/deploy.sh`. The deploy script is a manual Operator tool that syncs a
reviewed repository tree into the production target path named by the script,
defaults to dry-run, requires explicit `--apply` for changes, excludes Git
metadata, virtualenvs, caches, logs, backup state, and `.env` files, and does
not run migrations or systemd commands.

Systemd unit files present in `deploy/systemd/` define the runtime topology:
`duzman.service` is the umbrella unit, `duzman-health.service` runs
`duzman.runtime.run_health_server`, and `duzman-scheduler.service` runs
`duzman.runtime.run_scheduler`. `deploy/install_systemd.sh` installs the
umbrella, health, scheduler, daily backup service, and daily backup timer, and
its preflight checks the service environment file by stat only for owner and
mode `600`.

The runtime units load settings through systemd `EnvironmentFile`. This
architecture document records the intended unit roles from repository files
only; it does not assert live service status.

### Day 9D — Encrypted local backup

`deploy/backup.sh` creates local encrypted backups through
`duzman-backup.service`. The script dumps selected database tables, copies
configuration inputs and `.env` into a temporary archive, encrypts the archive
with GPG AES256 using a passphrase sourced from the process environment, sends
the encrypted result to the configured Telegram backup channel when it is under
the 50 MB Telegram limit, and applies local retention.

The Day 9D systemd files are `duzman-backup.service` and
`duzman-backup.timer`; the timer runs daily at 02:30 UTC. Local retention is
`RETENTION_COUNT=7` in `deploy/backup.sh` and is also described in
`deploy/README.md` as keeping the last 7 local backups.

Commit `3a23d60` fixed the Day 9D GPG home issue under the systemd sandbox by
setting `GNUPGHOME` inside the temporary backup workdir before encryption.
`docs/process/REVIEW_PROTOCOL.md` records the review-process lesson for that
fix.

### Day 10A and Day 10B — OneDrive weekly backup

The repository does not contain a separate Day 10A spec file under
`docs/specs/`. Current OneDrive backup implementation evidence is the Day 10B
commit `ee687f2` and the deploy files it added.

`deploy/onedrive_upload.sh` uploads the latest local encrypted backup through
rclone to the `onedrive` remote path `Duzman/Backups`, verifies the uploaded
file by remote listing and size, writes a JSON Lines manifest, applies remote
retention, and sends success or failure notifications through Telegram chat
ids loaded from settings. `deploy/install_onedrive_backup.sh` installs
`duzman-onedrive-backup.service` and `duzman-onedrive-backup.timer`.

`duzman-onedrive-backup.timer` runs weekly on Sunday at 03:00 UTC, after the
daily 02:30 UTC local backup. Remote retention is `RETENTION_COUNT=12` in
`deploy/onedrive_upload.sh` and is described in `deploy/README.md` as
independent 12-week retention.

The upload manifest is
`/opt/duzman/backups/onedrive_upload_manifest.jsonl`. Each JSON line records
`uploaded_at`, `file`, `sha256`, `size_bytes`, and `remote`, as written by
`append_manifest()` in `deploy/onedrive_upload.sh`.

### Operational topology (post Day 10B)

- `duzman.service` — umbrella service that binds the health and scheduler
  child services.
- `duzman-health.service` — local health service running the health runtime
  entrypoint.
- `duzman-scheduler.service` — long-running runtime scheduler service.
- `duzman-backup.service` — oneshot daily encrypted backup service.
- `duzman-backup.timer` — daily backup timer at 02:30 UTC.
- `duzman-onedrive-backup.service` — oneshot weekly OneDrive backup upload.
- `duzman-onedrive-backup.timer` — weekly OneDrive backup timer at Sunday
  03:00 UTC.

### Settings tolerance (post incident 2026-05-24)

`src/duzman/settings.py` now sets `extra="ignore"` in
`Settings.model_config`, merged as commit `5a252c0` in PR #68, so
forward-compatible additions to `.env` do not raise Pydantic validation
errors when settings are loaded at process start. The corresponding review
lesson is recorded in `docs/process/REVIEW_PROTOCOL.md`.

`database_url`, `anthropic_api_key`, `telegram_bot_token`, and
`duzman_api_key` are now `SecretStr`, matching the existing
`coinglass_api_key` precedent. This is defense-in-depth against accidental
secret rendering in repr, dumps, or future `ValidationError` `input_value`
scenarios; it does not address the root cause of incident 2026-05-24, which
was fixed in PR #68 via `extra="ignore"`.

### Dev workflow — Codex git sandbox limitation

Inside the Codex CLI sandbox, `.git` is mounted read-only even though the
workspace tree is writable. The sanctioned manual git workflow is documented
in `docs/process/CODEX_GIT_WORKFLOW.md`.

### Current open scope

- Telegram multi-chat, webhook, inline buttons, and per-alert snooze
- Дашборд: FastAPI `/api/v1/` полностью, HTML + Plotly.js
- Caddy + HTTPS
- Retention job beyond the documented backup-retention scripts
- Daily digest

### Phase 1 — Pattern Tick Scheduler Wiring

- `src/duzman/runtime/market_data_scheduler.py` registers `pattern_tick_hourly`
  at XX:33 UTC, separate from existing XX:17, XX:18, and XX:23 jobs.
- The job runs `run_hourly_pattern_tick` with `dispatch_alerts=None`, so Phase 1
  is observation-only: AlertGate decisions may be persisted to `pattern_triggers`,
  but Telegram delivery, AI explanation rows, and external notification side
  effects are not connected.
- The full tick (evaluation + post-tick count) runs inside one `asyncio.run`
  call. The pattern tick owns its async database engine: a fresh `AsyncEngine`
  and `async_sessionmaker` are built inside the cycle and disposed in a
  `try/finally` block. No async resources are cached across APScheduler
  invocations because asyncpg Futures are bound to the event loop that created
  them, and each `asyncio.run` closes its loop on completion.
- Successful runs emit `pattern_tick_cycle_completed` with `allowed_count`,
  `total_matches`, and `elapsed_ms`. Failed runs emit `pattern_tick_cycle_failed`
  with `safe_error_message` and re-raise so APScheduler records the job failure.
