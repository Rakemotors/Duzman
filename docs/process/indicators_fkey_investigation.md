# Indicators FK investigation — Issue #72

## Symptom

Issue #72 reports that the scheduler indicator path reaches a PostgreSQL
foreign-key failure on `indicators_asset_fkey` during `run_indicator_cycle`.
This task did not read production data. Production seed-state confirmation is
left to the Operator through one sanitized read-only query.

## Repository evidence

`src/duzman/runtime/market_data_scheduler.py` builds `run_indicator_cycle` at
lines 73-81. That function calls `collect_indicators_job()` with a session
factory, `BinanceCollector`, `BybitCollector`, and `IndicatorRepository`, then
registers it at lines 83-86.

`src/duzman/scheduler/indicator_jobs.py` defines
`STAGE_A_INDICATOR_ASSETS = ("BTC", "ETH", "SOL", "SUI", "TON", "UNI")` at
line 33. `collect_indicators_job()` defaults to that tuple at line 41, loops
over the assets at line 49, accumulates `IndicatorRecord` values at lines
51-57, and persists all accumulated records through
`repository.save_indicators(session, records)` at line 67.

`src/duzman/repositories/indicator_repository.py` creates `Indicator` ORM rows
from supplied records at lines 27-39 and calls `session.flush()` at line 40.
There is no asset lookup, seed, or upsert in `save_indicators()`.

`src/duzman/db/models.py` defines `Asset` with primary key `symbol` at lines
28-35. The same file defines `Indicator.asset` as
`ForeignKey("assets.symbol")` at line 78. It also defines
`PriceSnapshot.asset` as `ForeignKey("assets.symbol")` at line 58.

`src/duzman/repositories/price_snapshots.py` has the same persistence shape for
price snapshots: it copies `snapshot.asset` into `PriceSnapshot.asset` at
lines 20-29, then calls `self.session.flush()` at line 31. It does not upsert
or ensure the corresponding `assets` row first.

The existing indicator repository tests used SQLite and a repository-local
table setup. After this task, `tests/test_indicator_repository.py` keeps that
fixture style and enables the FK in its local `indicators` table at lines
97-125.

## Confirmed structural facts

The initial Alembic migration creates `assets` at
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py` lines 22-34.
It creates `indicators.asset` with `sa.ForeignKey("assets.symbol")` at lines
49-58. Because the PostgreSQL constraint is unnamed in the migration,
PostgreSQL derives the default constraint name; for this table and column that
matches the reported `indicators_asset_fkey`.

`IndicatorRepository.save_indicators()` does not validate asset existence
before flush. The database FK is the first hard boundary for missing assets
when records are inserted.

The indicator job source of assets is the constant tuple in
`src/duzman/scheduler/indicator_jobs.py` line 33, not a database query. This
differs from runtime jobs such as `src/duzman/runtime/coinglass_jobs.py`, where
`collect_liquidations_once()` loops over `_enabled_assets(session)` at lines
76-80 and `_enabled_assets()` reads `Asset.symbol` rows at lines 182-188, and
`src/duzman/runtime/farside_jobs.py`, where `_enabled_etf_assets()` reads
enabled BTC/ETH assets at lines 121-127.

`BinanceCollector.supported_symbols` maps uppercase Stage A asset symbols to
USDT symbols at `src/duzman/collectors/binance.py` lines 54-61. Its
`_normalize_asset_symbol()` uppercases input at line 210, accepts direct asset
symbols at lines 211-212, maps Binance symbols back to asset symbols at lines
214-216, and returns uppercase asset symbols.

`BybitCollector.supported_symbols` maps uppercase Stage A asset symbols to
USDT symbols at `src/duzman/collectors/bybit.py` lines 53-60.
`fetch_mark_prices()` returns a `list[dict[str, Decimal | str]]` at lines
131-149. Each mark-price record created by `_fetch_symbol_mark_price()` has
shape `{"asset": asset_symbol, "mark_price": Decimal(...)}` at lines 240-243.
The `asset_symbol` comes from `_normalize_asset_symbol()`, which uppercases
input at line 365 and returns uppercase Stage A symbols at line 368.

## Confirmed negative

All Alembic files under `src/duzman/db/alembic/versions/` were opened:

- `2b8f4f6c9a1e_normalize_price_snapshots.py`
- `5c1c8f9d0e2a_create_source_health_checks.py`
- `8f3a2c1b9d6e_add_alert_explanations.py`
- `9b7c6d5e4f3a_add_telegram_message_id.py`
- `a7c9f1d4e8b2_create_liquidation_heatmap.py`
- `b009e25bfab4_initial_schema.py`
- `c0d2f8e4a9b1_canonicalize_price_snapshots.py`
- `d7e1f2a3b4c5_add_alert_deliveries_and_telegram_state.py`

Repository grep over those files found `assets` references only for table
creation, FK definitions, and table drop. No migration performs `INSERT` into
`assets`; no migration calls `op.bulk_insert` for `assets`; no migration calls
`op.execute` with an `INSERT ... assets` statement.

All files directly under `src/duzman/runtime/` were inspected:

- `__init__.py`
- `alternative_me_jobs.py`
- `coingecko_global_jobs.py`
- `coinglass_jobs.py`
- `farside_jobs.py`
- `market_data_scheduler.py`
- `run_ai_explanation_smoke.py`
- `run_ai_explanation_worker.py`
- `run_health_server.py`
- `run_market_data_collection_once.py`
- `run_scheduler.py`
- `verify_local_database.py`
- `verify_read_only_api.py`
- `verify_telegram_base.py`

`src/duzman/main.py` is absent. No inspected runtime file contains an
asset-bootstrap hook or an upsert-on-startup hook for Stage A assets.

## Reproducer test

The reproducer lives in `tests/test_indicator_repository.py`.

`test_indicator_repository_raises_integrity_error_without_asset()` at lines
74-81 creates the existing SQLite-style indicator repository test database
without inserting an `assets` row, constructs the minimal BTC RSI
`IndicatorRecord`, calls `IndicatorRepository.save_indicators()`, and asserts
that `sqlalchemy.exc.IntegrityError` is raised with SQLite's equivalent
`FOREIGN KEY constraint failed` message.

`test_indicator_repository_saves_indicator_when_asset_exists()` at lines 84-94
pre-inserts `Asset(symbol="BTC")`, saves the same class of indicator record,
commits, and asserts that one row exists in `indicators`. Together the pair
captures the invariant: the asset must exist before indicator persistence.

Run the focused reproducer with:

```bash
pytest tests/test_indicator_repository.py -q
```

## Ranked hypotheses

1. Most likely: production `assets` is missing at least one symbol from
   `STAGE_A_INDICATOR_ASSETS`.

   Supporting evidence: the indicator job persists records for the hard-coded
   Stage A tuple from `indicator_jobs.py` line 33; `Indicator.asset` points to
   `assets.symbol` in `models.py` line 78; no migration or runtime bootstrap
   seeds those asset rows. Distinguishing evidence: the Operator should run a
   sanitized read-only query on production and compare the returned symbols to
   `BTC, ETH, SOL, SUI, TON, UNI`.

2. Possible: production `assets` contains only the subset used by earlier
   price or ETF flows.

   Supporting evidence: some runtime jobs read enabled assets from the
   database (`coinglass_jobs.py` lines 182-188 and `farside_jobs.py` lines
   121-127), while the indicator job does not. Distinguishing evidence: the
   same sanitized production symbol list will show which subset exists.

3. Less likely from repository evidence: collector normalization emits a
   lowercase or exchange-specific symbol that does not match `assets.symbol`.

   Counter-evidence: Binance and Bybit both normalize to uppercase Stage A
   asset symbols. Binance returns uppercase asset symbols via
   `_normalize_asset_symbol()` at `binance.py` lines 209-216; Bybit returns
   uppercase asset symbols through `_normalize_asset_symbol()` at `bybit.py`
   lines 364-368 and mark-price records with key `"asset"` at lines 240-243.

## Proposed next-task fix options

Option (a): idempotent Alembic seed migration of `STAGE_A_INDICATOR_ASSETS`.
This makes seed state explicit and reviewable at schema level. It is simple
and deterministic, but it creates another place where the Stage A asset list
can drift from scheduler and collector constants.

Option (b): runtime `AssetRepository.ensure_exists` upsert called before
indicator persistence, and before price snapshot persistence for symmetry.
This makes ingestion resilient to missing seed state and covers the same FK
structure in `price_snapshots`, but it moves canonical seed behavior into
runtime writes and broadens the write surface of ingestion paths.

Option (c): hybrid: seed migration as canonical source of truth plus a
single-source constant for the Stage A asset list shared by scheduler,
collectors, and seed. This has the most moving parts, but it addresses both
the missing seed and drift risks.

Recommendation: prefer option (c) if the next task can afford the small
coordination refactor; otherwise option (a) is the narrowest immediate fix.
Do not implement any of these in this investigation PR.

## Out-of-scope items

PR #71, AI explanations, Telegram delivery, deploy/systemd behavior,
credentials, production writes, Alembic schema changes, and any trading,
order, account, or private exchange paths are out of scope for this
investigation.
