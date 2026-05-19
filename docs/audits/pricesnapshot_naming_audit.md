# PriceSnapshot naming audit

Дата: 2026-05-19
Коммит main на момент audit: 8f3f0a0
Author: codex-cli
Refs: Issue #7, docs/TZ.md Приложение Б (Known schema drift)

## 1. Цель

Цель audit - зафиксировать фактическое использование имён полей
`PriceSnapshot` перед отдельной задачей на канонизацию схемы. Текущая
DDL в docs/TZ.md описывает `asset/ts/price_usd`, а фактические ORM,
миграция и код используют `symbol/collected_at/price`.

Audit готовит решение Operator между вариантом B (обновить TZ DDL под
код) и вариантом C (переименовать поля в коде/БД под проектный стандарт
`asset/ts/price_usd` с сохранением дополнительных полей). В рамках audit
код, миграции, тесты и runtime не изменялись.

## 2. Текущее состояние модели PriceSnapshot

### 2.1. Определение в ORM

Модель определена в `src/duzman/db/models.py:26`, таблица
`price_snapshots` - в `src/duzman/db/models.py:27`.

Поля модели:

- `id`: `BigInteger().with_variant(Integer, "sqlite")`, primary key,
  autoincrement, `src/duzman/db/models.py:39`.
- `source`: `String(20)`, `nullable=False`,
  `src/duzman/db/models.py:44`.
- `symbol`: `String(10)`, FK на `assets.symbol`, `nullable=False`,
  `src/duzman/db/models.py:45`.
- `quote_currency`: `String(10)`, `nullable=False`,
  `src/duzman/db/models.py:46`.
- `price`: `Numeric(20, 8)`, `nullable=False`,
  `src/duzman/db/models.py:47`.
- `collected_at`: `DateTime(timezone=True)`, `nullable=False`,
  `src/duzman/db/models.py:48`.
- `created_at`: `DateTime(timezone=True)`, `server_default=func.now()`,
  `nullable=False`, `src/duzman/db/models.py:49`.
- `raw_payload`: `JSON`, `nullable=True`,
  `src/duzman/db/models.py:52`.
- `volume_24h_quote`: `Numeric(20, 2)`, nullable by default,
  `src/duzman/db/models.py:53`.
- `price_change_24h_pct`: `Numeric(8, 4)`, nullable by default,
  `src/duzman/db/models.py:54`.

Indexes:

- `ix_price_snapshots_source_symbol_collected_at` on
  `source/symbol/collected_at`, `src/duzman/db/models.py:29`.
- `ix_price_snapshots_collected_at` on `collected_at`,
  `src/duzman/db/models.py:35`.
- `ix_price_snapshots_source` on `source`,
  `src/duzman/db/models.py:36`.

### 2.2. Состояние БД (по последней миграции)

Последняя миграция, которая меняла `price_snapshots`, -
`src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py`.
Revision id: `2b8f4f6c9a1e`, дата создания:
`src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:5`.

Миграция сделала следующее:

- Удалила старый индекс `ix_price_snapshots_ts_asset`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:22`.
- Переименовала `ts` -> `collected_at`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:23`.
- Переименовала `asset` -> `symbol`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:30`.
- Переименовала `price_usd` -> `price` и сделала `nullable=False`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:37`.
- Переименовала `volume_24h_usd` -> `volume_24h_quote`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:45`.
- Сделала `source` `nullable=False`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:52`.
- Добавила `quote_currency`, затем сняла server default,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:59`
  and `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:63`.
- Добавила `created_at`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:69`.
- Добавила `raw_payload`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:78`.
- Удалила `price_change_7d_pct`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:79`.
- Создала индексы на `source/symbol/collected_at`, `collected_at`,
  `source`, `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:80`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:85`,
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:90`.

Начальная миграция создавала canonical TZ-форму `ts/asset/price_usd`:
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:36`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:39`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:40`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:41`.

## 3. Использование полей в коде

### 3.1. `symbol` (кандидат на переименование в `asset`)

ORM:

- `src/duzman/db/models.py:45` - колонка `PriceSnapshot.symbol`, FK на
  `assets.symbol`.
- `src/duzman/db/models.py:29` - индекс включает `symbol`.

Repositories:

- `src/duzman/repositories/price_snapshots.py:22` - сохраняет
  `MarketDataSnapshot.symbol` в `PriceSnapshot.symbol`.
- `src/duzman/repositories/price_snapshots.py:41` - фильтр
  `latest_by_source_symbol()` по `PriceSnapshot.symbol`.
- `src/duzman/repositories/price_snapshots.py:56` - опциональный фильтр
  `list_latest(symbol=...)`.
- `src/duzman/db/repositories/snapshot_repository.py:72` - pattern
  snapshot repository ищет последний price snapshot по asset через
  `PriceSnapshot.symbol`.
- `src/duzman/db/repositories/snapshot_repository.py:110` - диапазонный
  запрос price snapshots фильтрует по `PriceSnapshot.symbol`.

Services:

- `src/duzman/services/market_data_fetchers.py:40` - переносит
  `MarketDataSnapshot.symbol` при override `collected_at`.
- `src/duzman/services/ingestion_health_alerts.py:27` - Protocol для
  health rows требует поле `symbol`.
- `src/duzman/services/ingestion_health_alerts.py:156` - stale alert
  возвращает `latest_snapshot.symbol`.

Runtime:

- `src/duzman/runtime/coinglass_jobs.py:194` - CoinGlass heatmap job
  ищет текущую цену по `PriceSnapshot.symbol`.

API / schemas:

- `src/duzman/api/schemas.py:15` - внешняя response schema
  `PriceSnapshotRead` отдаёт поле `symbol`.
- `src/duzman/api/routes/market_data.py:35` - query parameter называется
  `symbol`.
- `src/duzman/api/routes/market_data.py:44` - route передаёт query
  parameter в repository как `symbol`.
- `src/duzman/api/routes/market_data.py:84` - ingestion status собирает
  `symbols_seen` из `PriceSnapshot.symbol`.
- `src/duzman/api/routes/market_data.py:129` - JSON response получает
  `symbol=snapshot.symbol`.

Tests:

- `tests/test_price_snapshot_repository.py:34` - metadata test ожидает
  колонку `symbol`.
- `tests/test_price_snapshot_repository.py:52`,
  `tests/test_price_snapshot_repository.py:79`,
  `tests/test_price_snapshot_repository.py:103`,
  `tests/test_price_snapshot_repository.py:133` - test fixtures создают
  market snapshots с `symbol`.
- `tests/test_price_snapshot_repository.py:65`,
  `tests/test_price_snapshot_repository.py:90`,
  `tests/test_price_snapshot_repository.py:145` - assertions читают
  `saved.symbol` / `latest[0].symbol`.
- `tests/test_market_data_api.py:49`,
  `tests/test_market_data_api.py:61` - API seed data создаёт snapshots
  с `symbol`.
- `tests/test_market_data_api.py:135` - response shape ожидает ключ
  `symbol`.
- `tests/test_market_data_api.py:153`,
  `tests/test_market_data_api.py:161` - endpoint filter и assertion
  используют JSON/query `symbol`.
- `tests/test_market_data_ingestion.py:59` - persisted snapshots
  проверяются через `snapshot.symbol`.
- `tests/unit/patterns/test_snapshot.py:396` - тестовая SQLite DDL
  использует колонку `symbol`.
- `tests/unit/patterns/test_snapshot.py:488` - helper `_price()` создаёт
  `PriceSnapshot(symbol=asset)`.
- `tests/runtime/test_coinglass_jobs.py:178` - helper создаёт
  `PriceSnapshot(symbol=asset)`.

### 3.2. `collected_at` (кандидат на переименование в `ts`)

ORM:

- `src/duzman/db/models.py:48` - колонка `PriceSnapshot.collected_at`.
- `src/duzman/db/models.py:29` - составной индекс включает
  `collected_at`.
- `src/duzman/db/models.py:35` - отдельный индекс на `collected_at`.

Repositories:

- `src/duzman/repositories/price_snapshots.py:25` - сохраняет
  `MarketDataSnapshot.collected_at`.
- `src/duzman/repositories/price_snapshots.py:42` - сортирует latest query
  по `PriceSnapshot.collected_at.desc()`.
- `src/duzman/repositories/price_snapshots.py:59` - сортирует
  `list_latest()` по `PriceSnapshot.collected_at.desc()`.
- `src/duzman/db/repositories/snapshot_repository.py:75` - нижняя граница
  окна по `PriceSnapshot.collected_at`.
- `src/duzman/db/repositories/snapshot_repository.py:77` - верхняя граница
  окна по `PriceSnapshot.collected_at`.
- `src/duzman/db/repositories/snapshot_repository.py:78` - сортировка
  latest по `PriceSnapshot.collected_at.desc()`.
- `src/duzman/db/repositories/snapshot_repository.py:97` - nearest-row
  calculation использует `row.collected_at`.
- `src/duzman/db/repositories/snapshot_repository.py:111` and
  `src/duzman/db/repositories/snapshot_repository.py:112` - диапазонный
  запрос фильтрует по `PriceSnapshot.collected_at`.
- `src/duzman/db/repositories/snapshot_repository.py:114` - диапазонный
  запрос сортирует по `PriceSnapshot.collected_at.asc()`.

Services:

- `src/duzman/services/market_data_fetchers.py:43` - переносит
  caller-provided `collected_at` в normalized snapshot.
- `src/duzman/services/ingestion_health_alerts.py:28` - Protocol требует
  `collected_at`.
- `src/duzman/services/ingestion_health_alerts.py:141` - выбирает
  freshest snapshot по `row.collected_at`.
- `src/duzman/services/ingestion_health_alerts.py:142` - считает age по
  `latest_snapshot.collected_at`.
- `src/duzman/services/ingestion_health_alerts.py:157` - stale alert
  отдаёт `observed_at=latest_snapshot.collected_at`.

Runtime:

- `src/duzman/runtime/coinglass_jobs.py:195` - latest price query сортирует
  по `PriceSnapshot.collected_at.desc()`.

API / schemas:

- `src/duzman/api/schemas.py:19` - response schema отдаёт `collected_at`.
- `src/duzman/api/routes/market_data.py:69` - ingestion status считает
  `latest_price_snapshot_at` через `max(PriceSnapshot.collected_at)`.
- `src/duzman/api/routes/market_data.py:133` - response mapping отдаёт
  `collected_at=snapshot.collected_at`.

Tests:

- `tests/test_price_snapshot_repository.py:37` - metadata test ожидает
  колонку `collected_at`.
- `tests/test_price_snapshot_repository.py:55`,
  `tests/test_price_snapshot_repository.py:82`,
  `tests/test_price_snapshot_repository.py:106`,
  `tests/test_price_snapshot_repository.py:136` - fixtures задают
  `collected_at`.
- `tests/test_market_data_api.py:52`,
  `tests/test_market_data_api.py:64` - API seed data задаёт
  `collected_at`.
- `tests/test_market_data_api.py:139` - response shape ожидает ключ
  `collected_at`.
- `tests/test_market_data_api.py:204`,
  `tests/test_market_data_api.py:228`,
  `tests/test_market_data_api.py:249`,
  `tests/test_market_data_api.py:267` - health/status tests управляют
  freshness через `collected_at`.
- `tests/test_market_data_service.py:17`,
  `tests/test_market_data_service.py:22` - normalized snapshot хранит и
  возвращает `collected_at`.
- `tests/unit/patterns/test_snapshot.py:399` - тестовая SQLite DDL
  использует `collected_at`.
- `tests/unit/patterns/test_snapshot.py:491` - helper `_price()` задаёт
  `collected_at=ts`.
- `tests/runtime/test_coinglass_jobs.py:181` - helper задаёт
  `collected_at`.

### 3.3. `price` (кандидат на переименование в `price_usd`)

ORM:

- `src/duzman/db/models.py:47` - колонка `PriceSnapshot.price`.

Repositories:

- `src/duzman/repositories/price_snapshots.py:24` - сохраняет
  `MarketDataSnapshot.price`.
- `src/duzman/db/repositories/snapshot_repository.py:64` - returns
  `PriceSnapshot` rows whose `.price` later drives pattern calculations.
- `src/duzman/db/repositories/snapshot_repository.py:100` - returns price
  ranges whose `.price` later drives derived changes.

Services:

- `src/duzman/services/market_data_fetchers.py:42` - переносит
  `MarketDataSnapshot.price` при override `collected_at`.

Runtime:

- `src/duzman/runtime/coinglass_jobs.py:193` - selects
  `PriceSnapshot.price` as current price for liquidation heatmap.

API / schemas:

- `src/duzman/api/schemas.py:18` - response schema отдаёт `price`.
- `src/duzman/api/routes/market_data.py:132` - response mapping отдаёт
  `price=snapshot.price`.

Pattern Engine:

- `src/duzman/patterns/snapshot.py:309` - guards division by zero for BTC
  prices.
- `src/duzman/patterns/snapshot.py:311` - computes current asset/BTC price
  ratio from `.price`.
- `src/duzman/patterns/snapshot.py:312` - computes historical asset/BTC
  price ratio from `.price`.
- `src/duzman/patterns/snapshot.py:358` - guards previous `.price` before
  price-change calculation.
- `src/duzman/patterns/snapshot.py:360` - computes percentage price change
  from latest/previous `.price`.

Tests:

- `tests/test_price_snapshot_repository.py:36` - metadata test expects
  `price`.
- `tests/test_price_snapshot_repository.py:54`,
  `tests/test_price_snapshot_repository.py:81`,
  `tests/test_price_snapshot_repository.py:105`,
  `tests/test_price_snapshot_repository.py:135` - fixtures set `price`.
- `tests/test_price_snapshot_repository.py:66`,
  `tests/test_price_snapshot_repository.py:91`,
  `tests/test_price_snapshot_repository.py:114` - assertions read
  `saved.price` / `snapshot.price`.
- `tests/test_market_data_api.py:51`,
  `tests/test_market_data_api.py:63` - API seed data sets `price`.
- `tests/test_market_data_api.py:138` - response shape expects key
  `price`.
- `tests/test_market_data_service.py:16`,
  `tests/test_market_data_service.py:21`,
  `tests/test_market_data_service.py:55`,
  `tests/test_market_data_service.py:57` - service tests assert
  normalized `price`.
- `tests/unit/patterns/test_snapshot.py:398` - test DDL uses `price`.
- `tests/unit/patterns/test_snapshot.py:490` - helper `_price()` sets
  `price`.
- `tests/runtime/test_coinglass_jobs.py:180` - helper sets `price`.

### 3.4. Дополнительные поля, отсутствующие в TZ DDL

`quote_currency`:

- ORM: `src/duzman/db/models.py:46`.
- Migration: added at
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:59`.
- Collector DTO: `src/duzman/collectors/base.py:34`.
- Binance normalization sets quote currency to USDT:
  `src/duzman/collectors/binance.py:147`.
- CoinGecko normalization sets quote currency to USD:
  `src/duzman/collectors/coingecko.py:49`.
- Repository persists it:
  `src/duzman/repositories/price_snapshots.py:23`.
- API schema exposes it:
  `src/duzman/api/schemas.py:17`.
- API route maps it:
  `src/duzman/api/routes/market_data.py:131`.
- Tests cover metadata/API/fixtures at
  `tests/test_price_snapshot_repository.py:35`,
  `tests/test_market_data_api.py:137`,
  `tests/unit/patterns/test_snapshot.py:397`.
- Оценка: используется функционально как API-visible normalization field.

`created_at`:

- ORM: `src/duzman/db/models.py:49`.
- Migration: added at
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:69`.
- API schema exposes it:
  `src/duzman/api/schemas.py:20`.
- API route maps it:
  `src/duzman/api/routes/market_data.py:134`.
- Tests cover metadata/API/test DDL at
  `tests/test_price_snapshot_repository.py:38`,
  `tests/test_market_data_api.py:140`,
  `tests/unit/patterns/test_snapshot.py:400`.
- Оценка: используется функционально for API/read-model audit timestamp,
  though not in collector DTO.

`raw_payload`:

- ORM: `src/duzman/db/models.py:52`.
- Migration: added at
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:78`.
- Collector DTO carries it:
  `src/duzman/collectors/base.py:37`.
- Binance normalization stores raw payload:
  `src/duzman/collectors/binance.py:150`.
- CoinGecko normalization stores raw payload:
  `src/duzman/collectors/coingecko.py:52`.
- Repository persists a copied safe mapping:
  `src/duzman/repositories/price_snapshots.py:26`,
  `src/duzman/repositories/price_snapshots.py:62`.
- API route deliberately does not expose it; test asserts absence at
  `tests/test_market_data_api.py:144`.
- Tests assert persistence/no logging at
  `tests/test_price_snapshot_repository.py:67`,
  `tests/test_market_data_collection_job.py:109`.
- Оценка: нужно для аудита/persistence provenance; intentionally not
  exposed through public read API.

`volume_24h_quote`:

- ORM: `src/duzman/db/models.py:53`.
- Migration: rename from `volume_24h_usd` at
  `src/duzman/db/alembic/versions/2b8f4f6c9a1e_normalize_price_snapshots.py:45`.
- Collector DTO carries it:
  `src/duzman/collectors/base.py:38`.
- Binance normalization fills from `quoteVolume`:
  `src/duzman/collectors/binance.py:151`.
- CoinGecko normalization fills from `total_volume`:
  `src/duzman/collectors/coingecko.py:53`.
- Repository persists it:
  `src/duzman/repositories/price_snapshots.py:27`.
- API schema exposes it:
  `src/duzman/api/schemas.py:21`.
- API route maps it:
  `src/duzman/api/routes/market_data.py:135`.
- Tests cover it at `tests/test_market_data_api.py:141`,
  `tests/unit/patterns/test_snapshot.py:402`,
  `tests/test_binance_collector.py:55`,
  `tests/test_coingecko_collector.py:43`.
- Оценка: используется функционально as quote-denominated 24h volume in
  normalization and API.

## 4. Использование `asset/ts` в соседних таблицах

Модели, которые используют `asset` и `ts`:

- `Indicator`: `ts` at `src/duzman/db/models.py:64`, `asset` FK at
  `src/duzman/db/models.py:65`, index at `src/duzman/db/models.py:60`.
- `FundingRate`: `ts` at `src/duzman/db/models.py:79`, `asset` FK at
  `src/duzman/db/models.py:80`, index at `src/duzman/db/models.py:75`.
- `OpenInterest`: `ts` at `src/duzman/db/models.py:94`, `asset` FK at
  `src/duzman/db/models.py:95`, index at `src/duzman/db/models.py:90`.
- `LongShortRatio`: `ts` at `src/duzman/db/models.py:105`, `asset` FK at
  `src/duzman/db/models.py:106`.
- `Liquidation`: `ts` at `src/duzman/db/models.py:118`, `asset` FK at
  `src/duzman/db/models.py:119`.
- `LiquidationHeatmap`: `ts` at `src/duzman/db/models.py:138`,
  `asset` FK at `src/duzman/db/models.py:139`, index at
  `src/duzman/db/models.py:129`.
- `EtfFlow`: `asset` primary-key component at
  `src/duzman/db/models.py:150`; this model uses `date` instead of `ts`.
- `PatternTrigger`: `ts` at `src/duzman/db/models.py:168`, `asset` FK at
  `src/duzman/db/models.py:170`.

Initial migrations also use `asset/ts` for neighboring tables:
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:52`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:53`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:68`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:69`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:80`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:81`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:103`,
`src/duzman/db/alembic/versions/b009e25bfab4_initial_schema.py:104`.
Liquidation heatmap follows the same naming at
`src/duzman/db/alembic/versions/a7c9f1d4e8b2_create_liquidation_heatmap.py:25`
and `src/duzman/db/alembic/versions/a7c9f1d4e8b2_create_liquidation_heatmap.py:26`.

Вывод: `asset/ts` is the dominant DB naming standard for market metric
tables. `PriceSnapshot` is the outlier after migration
`2b8f4f6c9a1e`.

## 5. API-контракты

### 5.1. API schemas (src/duzman/api/schemas.py)

`PriceSnapshotRead` is the public Pydantic model for persisted price
snapshots, defined at `src/duzman/api/schemas.py:12`. It exposes:

- `symbol`, `src/duzman/api/schemas.py:15`.
- `source`, `src/duzman/api/schemas.py:16`.
- `quote_currency`, `src/duzman/api/schemas.py:17`.
- `price`, `src/duzman/api/schemas.py:18`.
- `collected_at`, `src/duzman/api/schemas.py:19`.
- `created_at`, `src/duzman/api/schemas.py:20`.
- `volume_24h_quote`, `src/duzman/api/schemas.py:21`.
- `price_change_24h_pct`, `src/duzman/api/schemas.py:22`.

There is explicit ORM -> schema mapping in
`src/duzman/api/routes/market_data.py:127`, not automatic one-to-one
model dumping. The mapping currently preserves the DB/ORM names in the
API response.

### 5.2. API routes (src/duzman/api/routes/market_data.py)

Endpoints using `price_snapshots`:

- `GET /api/market-data/prices/latest`,
  `src/duzman/api/routes/market_data.py:32`, returns
  `list[PriceSnapshotRead]`. JSON field names are `symbol`, `source`,
  `quote_currency`, `price`, `collected_at`, `created_at`,
  `volume_24h_quote`, `price_change_24h_pct` via
  `src/duzman/api/routes/market_data.py:127`.
- `GET /api/market-data/ingestion-status`,
  `src/duzman/api/routes/market_data.py:64`, reads
  `PriceSnapshot.collected_at` for `latest_price_snapshot_at` at
  `src/duzman/api/routes/market_data.py:69` and `PriceSnapshot.symbol`
  for `symbols_seen` at `src/duzman/api/routes/market_data.py:84`.
- `GET /api/market-data/ingestion-alerts`,
  `src/duzman/api/routes/market_data.py:113`, passes latest price
  snapshots into ingestion health evaluation at
  `src/duzman/api/routes/market_data.py:181`.

### 5.3. Внешние потребители

Repository-local docs mention the endpoint but do not define an external
consumer implementation:

- `README.md:43` lists `GET /api/market-data/prices/latest`.
- `docs/LOCAL_DEV_SETUP.md:174` lists the endpoint and
  `docs/LOCAL_DEV_SETUP.md:182` shows query parameters
  `symbol/source/limit`.
- `docs/ARCHITECTURE.md:88` lists `GET /api/market-data/prices/latest`
  as a read endpoint.
- `docs/TZ.md:655` lists `GET /api/market-data/prices/latest`.

Вне репозитория потребителей audit не обнаружил, требуется явное
подтверждение Operator.

## 6. Тесты

Тестовые файлы, которые обращаются к `PriceSnapshot` или к полям
`symbol/collected_at/price` в связанном market-data flow:

- `tests/test_price_snapshot_repository.py` - 5 tests. Metadata asserts
  `symbol/price/collected_at` at
  `tests/test_price_snapshot_repository.py:34`,
  `tests/test_price_snapshot_repository.py:36`,
  `tests/test_price_snapshot_repository.py:37`; fixtures and assertions
  use the fields at `tests/test_price_snapshot_repository.py:52`,
  `tests/test_price_snapshot_repository.py:54`,
  `tests/test_price_snapshot_repository.py:55`,
  `tests/test_price_snapshot_repository.py:65`,
  `tests/test_price_snapshot_repository.py:66`,
  `tests/test_price_snapshot_repository.py:114`,
  `tests/test_price_snapshot_repository.py:145`.
- `tests/test_market_data_api.py` - at least 6 tests share seeded
  `PriceSnapshot` data. Seed data uses `symbol/price/collected_at` at
  `tests/test_market_data_api.py:49`,
  `tests/test_market_data_api.py:51`,
  `tests/test_market_data_api.py:52`,
  `tests/test_market_data_api.py:61`,
  `tests/test_market_data_api.py:63`,
  `tests/test_market_data_api.py:64`; response shape asserts
  `symbol/price/collected_at` at `tests/test_market_data_api.py:135`,
  `tests/test_market_data_api.py:138`,
  `tests/test_market_data_api.py:139`.
- `tests/test_market_data_ingestion.py` - 2 tests create
  `PriceSnapshot.__table__` at `tests/test_market_data_ingestion.py:16`
  and assert saved `snapshot.symbol` at
  `tests/test_market_data_ingestion.py:59`.
- `tests/test_market_data_collection_job.py` - fake fetchers create
  `MarketDataSnapshot` rows with `symbol/price/collected_at` at
  `tests/test_market_data_collection_job.py:44`,
  `tests/test_market_data_collection_job.py:46`,
  `tests/test_market_data_collection_job.py:47`,
  `tests/test_market_data_collection_job.py:59`,
  `tests/test_market_data_collection_job.py:61`,
  `tests/test_market_data_collection_job.py:62`.
- `tests/test_runtime_market_data_scheduler.py` - fake fetchers create
  `MarketDataSnapshot` rows with `symbol/price/collected_at` at
  `tests/test_runtime_market_data_scheduler.py:31`,
  `tests/test_runtime_market_data_scheduler.py:33`,
  `tests/test_runtime_market_data_scheduler.py:34`,
  `tests/test_runtime_market_data_scheduler.py:44`,
  `tests/test_runtime_market_data_scheduler.py:46`,
  `tests/test_runtime_market_data_scheduler.py:47`.
- `tests/unit/patterns/test_snapshot.py` - custom SQLite DDL and helper
  use current field names at `tests/unit/patterns/test_snapshot.py:393`,
  `tests/unit/patterns/test_snapshot.py:396`,
  `tests/unit/patterns/test_snapshot.py:398`,
  `tests/unit/patterns/test_snapshot.py:399`,
  `tests/unit/patterns/test_snapshot.py:486`.
- `tests/runtime/test_coinglass_jobs.py` - helper creates
  `PriceSnapshot(symbol/price/collected_at)` at
  `tests/runtime/test_coinglass_jobs.py:176`,
  `tests/runtime/test_coinglass_jobs.py:178`,
  `tests/runtime/test_coinglass_jobs.py:180`,
  `tests/runtime/test_coinglass_jobs.py:181`.
- `tests/test_market_data_service.py` - tests normalized
  `MarketDataSnapshot.price/collected_at` at
  `tests/test_market_data_service.py:16`,
  `tests/test_market_data_service.py:17`,
  `tests/test_market_data_service.py:21`,
  `tests/test_market_data_service.py:22`.
- `tests/test_market_data_fetchers.py` - asserts normalized
  `snapshot.symbol` and `snapshot.price` at
  `tests/test_market_data_fetchers.py:38`,
  `tests/test_market_data_fetchers.py:39`,
  `tests/test_market_data_fetchers.py:72`,
  `tests/test_market_data_fetchers.py:73`.
- `tests/test_indicator_jobs.py` - fake spot snapshots use current DTO
  names at `tests/test_indicator_jobs.py:66`,
  `tests/test_indicator_jobs.py:68`,
  `tests/test_indicator_jobs.py:70`,
  `tests/test_indicator_jobs.py:71`.
- Collector tests assert DTO fields before persistence:
  `tests/test_binance_collector.py:52`,
  `tests/test_binance_collector.py:54`,
  `tests/test_coingecko_collector.py:40`,
  `tests/test_coingecko_collector.py:42`,
  `tests/test_coingecko_collector.py:45`.

Итого: at least 11 test files touch the current
`symbol/collected_at/price` naming either directly on `PriceSnapshot` or
through the normalized `MarketDataSnapshot` DTO used for persistence.

## 7. Naming standard: рекомендация

1. Фактические имена вне ORM: repositories, services, API routes,
   Pattern Engine, runtime jobs and tests use `symbol`, `collected_at`,
   and `price`. The main external API also exposes `symbol`,
   `collected_at`, and `price` through `PriceSnapshotRead`.

2. Каноническое именование проекта по соседним DB tables - `asset/ts`.
   Evidence: `Indicator`, `FundingRate`, `OpenInterest`,
   `LongShortRatio`, `Liquidation`, `LiquidationHeatmap`,
   `PatternTrigger` all use `asset/ts` (or `asset` with `date` for
   `EtfFlow`). `PriceSnapshot` is the only market metric outlier.
   For the price value itself, TZ uses `price_usd`; current code uses
   generic `price`.

3. Дополнительные поля:
   - `quote_currency`: functionally needed; it distinguishes Binance
     USDT quotes from CoinGecko USD quotes and is exposed by API.
   - `created_at`: functionally useful as persistence/audit timestamp
     and exposed by API.
   - `raw_payload`: needed for audit/provenance and repository tests,
     deliberately not exposed by API.
   - `volume_24h_quote`: functionally needed because incoming sources
     provide quote-denominated volume and API exposes it.

4. Recommendation: вариант C is preferred. Rename
   `symbol -> asset`, `collected_at -> ts`, and `price -> price_usd`
   to match the project DB standard and TZ, while preserving
   `quote_currency`, `created_at`, `raw_payload`,
   `volume_24h_quote`, and `price_change_24h_pct`. Variant B would
   codify the only outlier and keep Pattern Engine/repository naming
   inconsistent with neighboring tables.

5. Files requiring edits for вариант C:
   - ORM: `src/duzman/db/models.py`.
   - Migration: new file under
     `src/duzman/db/alembic/versions/`.
   - Repositories: `src/duzman/repositories/price_snapshots.py`,
     `src/duzman/db/repositories/snapshot_repository.py`.
   - Services: `src/duzman/services/market_data_fetchers.py`,
     `src/duzman/services/ingestion_health_alerts.py`.
   - Runtime: `src/duzman/runtime/coinglass_jobs.py`.
   - API: `src/duzman/api/schemas.py`,
     `src/duzman/api/routes/market_data.py`.
   - Pattern Engine: `src/duzman/patterns/snapshot.py`.
   - Scheduler DTO use: `src/duzman/scheduler/indicator_jobs.py`
     if `MarketDataSnapshot` is renamed too.
   - Collector DTO and producers if canonicalization includes the
     pre-persistence DTO: `src/duzman/collectors/base.py`,
     `src/duzman/collectors/binance.py`,
     `src/duzman/collectors/coingecko.py`.
   - Tests: `tests/test_price_snapshot_repository.py`,
     `tests/test_market_data_api.py`,
     `tests/test_market_data_ingestion.py`,
     `tests/test_market_data_collection_job.py`,
     `tests/test_runtime_market_data_scheduler.py`,
     `tests/unit/patterns/test_snapshot.py`,
     `tests/runtime/test_coinglass_jobs.py`,
     `tests/test_market_data_service.py`,
     `tests/test_market_data_fetchers.py`,
     `tests/test_indicator_jobs.py`,
     `tests/test_binance_collector.py`,
     `tests/test_coingecko_collector.py`.

## 8. Предлагаемый план миграции C (если рекомендован)

Рекомендован вариант C.

- Alembic `upgrade()`:
  - `op.drop_index("ix_price_snapshots_source_symbol_collected_at",
    table_name="price_snapshots")`
  - `op.drop_index("ix_price_snapshots_collected_at",
    table_name="price_snapshots")`
  - `op.alter_column("price_snapshots", "symbol",
    new_column_name="asset", existing_type=sa.String(10),
    existing_nullable=False)`
  - `op.alter_column("price_snapshots", "collected_at",
    new_column_name="ts", existing_type=sa.DateTime(timezone=True),
    existing_nullable=False)`
  - `op.alter_column("price_snapshots", "price",
    new_column_name="price_usd", existing_type=sa.Numeric(20, 8),
    existing_nullable=False)`
  - create indexes, for example
    `ix_price_snapshots_source_asset_ts` on `source/asset/ts`,
    `ix_price_snapshots_ts` on `ts`, keep
    `ix_price_snapshots_source` if unchanged.
- No data backfill should be required: all operations are column renames
  and index recreation; additional columns are preserved.
- Safety: PostgreSQL column renames are metadata operations. In dev
  this can run in one transaction. Production downtime risk is low but
  application code and DB migration must be deployed together because
  old code will query old column names.
- `downgrade()` should drop the new indexes, rename
  `asset -> symbol`, `ts -> collected_at`, `price_usd -> price`, and
  recreate old indexes.
- Code/test edits: use the file list in section 7.5.
- Estimated invasiveness: approximately 9 production source files if
  only persisted ORM/API/Pattern paths are renamed; approximately 12
  source files if the `MarketDataSnapshot` DTO is also canonicalized.
  Tests touched: approximately 12 files.

## 9. Открытые вопросы для Operator

- Should the public API keep backward-compatible JSON field names
  `symbol/collected_at/price`, or should API output also change to
  `asset/ts/price_usd`?
- Should `MarketDataSnapshot` (pre-persistence DTO) be canonicalized to
  `asset/ts/price_usd`, or should the rename stop at ORM/DB and use an
  explicit DTO -> ORM mapping?
- Is a temporary compatibility layer needed for existing dev DB data or
  downstream dashboard clients outside the repository?
- Should the future migration PR update docs/TZ.md DDL after code/DB
  canonicalization, or is TZ already considered canonical enough after
  removing the known-drift block?
