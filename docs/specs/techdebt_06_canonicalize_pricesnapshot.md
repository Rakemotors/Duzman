# techdebt_06: PriceSnapshot schema canonicalization (variant C)

Based on: Техническое задание v1.7 от 2026-05-19 (docs/TZ.md)
Based on audit: docs/audits/pricesnapshot_naming_audit.md

## Issue

Closes #7

Это финальная задача по техдолгу #7. После её мержа известный schema drift в Приложении Б TZ должен быть устранён, а Issue #7 закрыт.

## Контекст

Audit `docs/audits/pricesnapshot_naming_audit.md` (commit 8f3f0a0 на main) подтвердил, что:
- Все соседние market-metric таблицы используют `asset/ts` (`Indicator`, `FundingRate`, `OpenInterest`, `LongShortRatio`, `Liquidation`, `LiquidationHeatmap`, `PatternTrigger`).
- `PriceSnapshot` — единственный outlier с `symbol/collected_at/price` после миграции `2b8f4f6c9a1e_normalize_price_snapshots` (2026-05-15).
- Дополнительные поля `quote_currency`, `created_at`, `raw_payload`, `volume_24h_quote` функционально используются и должны быть сохранены.
- Внешних потребителей API в репозитории не обнаружено (раздел 5.3 audit), требуется явное подтверждение Operator через preflight.

Решение Operator (1/1/1 с preflight guard):
1. Полная канонизация: БД, ORM, DTO, API schema, API JSON — все используют `asset/ts/price_usd/volume_24h_usd`.
2. `MarketDataSnapshot` DTO канонизировать тоже.
3. Compatibility layer не делать, при условии прохождения preflight.

Целевые переименования:
- `symbol → asset`
- `collected_at → ts`
- `price → price_usd`

Сохраняются без переименования: `volume_24h_quote`, `quote_currency`, `created_at`, `raw_payload`, `price_change_24h_pct`, `source`, `id`.

ВАЖНО: `volume_24h_quote` сознательно НЕ переименовывается в `volume_24h_usd`. Причина: Binance отдаёт объём в USDT, CoinGecko в USD; имя `_usd` было бы misleading. Пара `volume_24h_quote + quote_currency` семантически точнее и честнее описывает данные. В этом месте TZ DDL обновляется под более корректную доменную модель кода, а не наоборот.

## Зона спецификации

Файлы и каталоги, доступные исполнителю для записи:

ORM и миграции:
- `src/duzman/db/models.py`
- `src/duzman/db/alembic/versions/` (создание нового файла миграции)

Repositories:
- `src/duzman/repositories/price_snapshots.py`
- `src/duzman/db/repositories/snapshot_repository.py`

Services и runtime:
- `src/duzman/services/market_data_fetchers.py`
- `src/duzman/services/ingestion_health_alerts.py`
- `src/duzman/services/market_data_ingestion.py`
- `src/duzman/services/market_data_collection_job.py`
- `src/duzman/runtime/coinglass_jobs.py`
- `src/duzman/scheduler/indicator_jobs.py` (если затрагивается через DTO)

API:
- `src/duzman/api/schemas.py`
- `src/duzman/api/routes/market_data.py`

Pattern Engine:
- `src/duzman/patterns/snapshot.py`

Collector DTO:
- `src/duzman/collectors/base.py`
- `src/duzman/collectors/binance.py`
- `src/duzman/collectors/coingecko.py`

Tests:
- `tests/test_price_snapshot_repository.py`
- `tests/test_market_data_api.py`
- `tests/test_market_data_ingestion.py`
- `tests/test_market_data_collection_job.py`
- `tests/test_runtime_market_data_scheduler.py`
- `tests/unit/patterns/test_snapshot.py`
- `tests/runtime/test_coinglass_jobs.py`
- `tests/test_market_data_service.py`
- `tests/test_market_data_fetchers.py`
- `tests/test_indicator_jobs.py`
- `tests/test_binance_collector.py`
- `tests/test_coingecko_collector.py`

Docs:
- `docs/TZ.md` (только удаление known-drift блока, см. ниже)

Файлы вне этого списка НЕ изменяются. В частности, НЕ трогать AGENTS.md, .claude/skills/duzman-conventions/SKILL.md, README.md, ARCHITECTURE.md, LOCAL_DEV_SETUP.md, другие миграции, другие модели.

## Preflight guard (обязательно, до любых изменений)

Перед началом правок выполнить и приложить вывод в PR-описание:

1. Подтвердить отсутствие внешних потребителей старых JSON-имён:
   ```
   grep -rn -E '"symbol"|"collected_at"|"price"|"volume_24h_quote"' --include="*.md" .
   grep -rn -E "MarketDataSnapshot|PriceSnapshot" --include="*.md" .
   grep -rn -E 'symbol|collected_at|volume_24h_quote' --include="*.yaml" --include="*.yml" --include="*.json" --include="*.toml" .
   ```
   Анализ: любая ссылка на старые имена в документации/конфигах должна быть либо обновлена в этом PR (если файл в зоне спецификации), либо явно перечислена в PR-описании как «остаётся на старых именах — НЕ публичный контракт» (если файл вне зоны).

2. Подтвердить отсутствие в коде вне зоны спецификации:
   ```
   git grep -nE '\.symbol\b|\.collected_at\b|\.volume_24h_quote\b' -- 'src/**'
   ```
   Все вхождения должны попадать в зону спецификации. Если найден файл вне зоны — остановиться и эскалировать Operator-у.

3. Подтвердить, что в репозитории нет:
   - Custom GPT action schema (`*.openapi.*`, `*.gpt.*`, `*.action.*`)
   - Frontend-кода (`*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.vue`)
   - Telegram-бот шаблонов с явной зависимостью от старых JSON-имён

   ```
   find . -name "*.openapi.*" -o -name "*.gpt.*" -o -name "*.action.*"
   find . -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.vue" | grep -v node_modules
   ```

Если любая из проверок выявляет неоднозначность — остановиться, не делать правки, вернуть отчёт в PR-описании или коммент к Issue #7.

## Что нужно сделать

### Шаг 1. Alembic миграция

Создать новый файл в `src/duzman/db/alembic/versions/` с осмысленным именем (например, `c0d2f8e4a9b1_canonicalize_price_snapshots.py`). `down_revision` — `a7c9f1d4e8b2` (текущая голова).

`upgrade()`:
```
op.drop_index("ix_price_snapshots_source_symbol_collected_at", table_name="price_snapshots")
op.drop_index("ix_price_snapshots_collected_at", table_name="price_snapshots")
op.alter_column("price_snapshots", "symbol", new_column_name="asset",
                existing_type=sa.String(10), existing_nullable=False)
op.alter_column("price_snapshots", "collected_at", new_column_name="ts",
                existing_type=sa.DateTime(timezone=True), existing_nullable=False)
op.alter_column("price_snapshots", "price", new_column_name="price_usd",
                existing_type=sa.Numeric(20, 8), existing_nullable=False)
op.create_index("ix_price_snapshots_source_asset_ts", "price_snapshots",
                ["source", "asset", "ts"])
op.create_index("ix_price_snapshots_ts", "price_snapshots", ["ts"])
```

`volume_24h_quote` НЕ переименовывается. Колонка остаётся с тем же именем.

`downgrade()` — симметричная операция: восстановить старые имена колонок и индексы. Никаких drop column, никакого изменения типов или nullable.

ВАЖНО: миграция должна быть metadata-only (rename + index recreation), без `op.add_column`/`op.drop_column` для существующих данных. Никакого data backfill. `quote_currency`, `created_at`, `raw_payload`, `price_change_24h_pct`, `source`, `id` остаются нетронутыми.

### Шаг 2. ORM модель

В `src/duzman/db/models.py` в классе `PriceSnapshot`:
- Переименовать атрибуты `symbol → asset`, `collected_at → ts`, `price → price_usd`.
- Обновить `__table_args__`: индекс `ix_price_snapshots_source_symbol_collected_at → ix_price_snapshots_source_asset_ts` (колонки `source/asset/ts`), индекс `ix_price_snapshots_collected_at → ix_price_snapshots_ts` (колонка `ts`). Индекс `ix_price_snapshots_source` оставить как есть.
- FK на `assets.symbol` для поля `asset` сохранить (это FK на `Asset.symbol` — PK таблицы assets, остаётся неизменным).
- Остальные поля (`id`, `source`, `quote_currency`, `price_usd`, `created_at`, `raw_payload`, `price_change_24h_pct`, `volume_24h_quote`) не менять (за исключением переименований выше).

### Шаг 3. Collector DTO

В `src/duzman/collectors/base.py` в классе `MarketDataSnapshot`:
- Переименовать атрибуты `symbol → asset`, `collected_at → ts`, `price → price_usd`.
- `volume_24h_quote` оставить без переименования.
- Остальные поля DTO оставить.

В `src/duzman/collectors/binance.py` и `src/duzman/collectors/coingecko.py`:
- Обновить нормализацию: имена ключей передаваемых в `MarketDataSnapshot(...)` соответствуют новым атрибутам.

### Шаг 4. Repositories, services, runtime, API, pattern engine

Во всех файлах из «Зоны спецификации» обновить все вхождения:
- `.symbol → .asset` (только для `PriceSnapshot` и `MarketDataSnapshot`)
- `.collected_at → .ts` (только для `PriceSnapshot` и `MarketDataSnapshot`)
- `.price → .price_usd` (только для `PriceSnapshot` и `MarketDataSnapshot`)
- Query parameters в API routes (`symbol` → `asset` в URL, если применимо — см. ниже)
- `.volume_24h_quote` НЕ переименовывается, остаётся как есть.

ВАЖНО: 
- В коде ЕСТЬ другие модели и сущности, у которых поле `.symbol` или `.asset` имеет своё значение (`Asset.symbol`, `Asset.asset`, `Indicator.asset` и т.п.). Переименование `.symbol → .asset` применяется ТОЛЬКО к атрибутам `PriceSnapshot` и `MarketDataSnapshot`, НЕ ко всем `.symbol` в коде.
- В частности, `Asset.symbol` — это PK таблицы `assets`, его НЕ трогать.

### Шаг 5. API schemas и JSON-контракт

В `src/duzman/api/schemas.py` в `PriceSnapshotRead`:
- Переименовать поля: `symbol → asset`, `collected_at → ts`, `price → price_usd`.
- Сохранить без переименования: `source`, `quote_currency`, `volume_24h_quote`, `created_at`, `price_change_24h_pct`.

В `src/duzman/api/routes/market_data.py`:
- В query parameter endpoint `/api/market-data/prices/latest` переименовать `symbol → asset`.
- Маппинг ORM → schema обновить под новые имена.
- В `/api/market-data/ingestion-status`: `latest_price_snapshot_at` строится из `PriceSnapshot.ts` (вместо `collected_at`); `symbols_seen` переименовать в `assets_seen` (т.к. это новое поле в JSON).
- Любые другие ключи JSON, связанные со старой схемой — переименовать соответственно.

### Шаг 6. Тесты

Обновить ВСЕ тесты из «Зоны спецификации»:
- Имена полей в фикстурах, factory-функциях, helper-ах (`_price()`, `_market_snapshot()` и т.п.).
- Имена ключей в assertions на JSON-ответы API.
- Имена колонок в тестовых SQLite DDL (`tests/unit/patterns/test_snapshot.py`).
- Metadata-проверки (`tests/test_price_snapshot_repository.py:34-37`).

Все 268 тестов должны остаться зелёными. Если в процессе обнаружится, что какой-то тест требует переименования полей в местах, не упомянутых в audit — это допустимо и не считается выходом за зону спецификации, при условии что файл сам по себе в whitelist.

### Шаг 7. Применение миграции к dev DB

После полного обновления кода и тестов:
```
.venv/bin/python -m alembic upgrade head
```

Запускается ТОЛЬКО на dev DB на VPS (~/duzman). НЕ трогать /opt/duzman/.env и prod alembic upgrade.

После успешного применения проверить:
```
.venv/bin/python -c "from sqlalchemy import inspect; from duzman.db.session import sync_engine; print([c['name'] for c in inspect(sync_engine).get_columns('price_snapshots')])"
```
Ожидается, что среди колонок есть `asset`, `ts`, `price_usd`, `volume_24h_usd` и нет `symbol`, `collected_at`, `price`, `volume_24h_quote`.

### Шаг 8. Обновление TZ DDL и удаление known-drift блока

В `docs/TZ.md` в Приложении Б:

1. Обновить DDL `CREATE TABLE price_snapshots (...)` под фактическую каноническую схему:
   ```
   CREATE TABLE price_snapshots (
       id BIGSERIAL PRIMARY KEY,
       ts TIMESTAMPTZ NOT NULL,
       asset VARCHAR(10) REFERENCES assets(symbol),
       source VARCHAR(20) NOT NULL,
       quote_currency VARCHAR(10) NOT NULL,
       price_usd NUMERIC(20,8) NOT NULL,
       volume_24h_quote NUMERIC(20,2),
       price_change_24h_pct NUMERIC(8,4),
       created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       raw_payload JSONB
   );
   CREATE INDEX ix_price_snapshots_source_asset_ts ON price_snapshots(source, asset, ts);
   CREATE INDEX ix_price_snapshots_ts ON price_snapshots(ts DESC);
   CREATE INDEX ix_price_snapshots_source ON price_snapshots(source);
   ```
   Старый индекс `idx_price_ts_asset` удалить из DDL.

2. Удалить полностью блок `> Known schema drift (PriceSnapshot, на 19.05.2026)` (~30 строк), который был добавлен в PR #15 (commit 8fc1388).

Журнал изменений в шапке TZ и таблицу версий внизу TZ — НЕ трогать. Это PATCH-уровневая нормализация DDL под фактическую более корректную доменную модель (см. обоснование `volume_24h_quote` в разделе «Контекст»).

## Definition of done

- [ ] Preflight guard выполнен, результаты приложены в PR-описание.
- [ ] Создан новый файл миграции в `src/duzman/db/alembic/versions/` с `down_revision = "a7c9f1d4e8b2"`.
- [ ] Миграция metadata-only: только rename column и index recreation, никаких add/drop column, никакого data backfill.
- [ ] В `PriceSnapshot` (ORM) атрибуты `asset`, `ts`, `price_usd` присутствуют; `symbol`, `collected_at`, `price` отсутствуют.
- [ ] В `PriceSnapshot` (ORM) сохранены `id`, `source`, `quote_currency`, `volume_24h_quote`, `created_at`, `raw_payload`, `price_change_24h_pct`.
- [ ] `volume_24h_quote` в коде и в TZ DDL НЕ переименован.
- [ ] В `MarketDataSnapshot` (DTO) аналогичное переименование `symbol/collected_at/price`.
- [ ] Все файлы из «Зоны спецификации» обновлены под новые имена.
- [ ] В `PriceSnapshotRead` (API schema) поля переименованы.
- [ ] Query parameter `/api/market-data/prices/latest?symbol=...` переименован в `?asset=...`.
- [ ] `Asset.symbol` НЕ переименован (это PK другой таблицы).
- [ ] `Indicator.asset`, `FundingRate.asset` и т.п. НЕ затронуты.
- [ ] Миграция применена к dev DB на VPS (`alembic upgrade head` завершён успешно).
- [ ] В `docs/TZ.md` DDL `CREATE TABLE price_snapshots (...)` обновлён под фактическую каноническую схему (`ts/asset/price_usd/volume_24h_quote/quote_currency/raw_payload/created_at`, индексы `ix_price_snapshots_*`).
- [ ] Known schema drift блок из `docs/TZ.md` удалён.
- [ ] Журнал изменений и таблица версий TZ не изменены.
- [ ] Все 268 тестов проходят: `.venv/bin/python -m pytest -q`.
- [ ] Файлы вне «Зоны спецификации» НЕ изменены.

## Проверки

```
git grep -nE '\.symbol\b' -- 'src/duzman/db/models.py' 'src/duzman/repositories/' 'src/duzman/db/repositories/' 'src/duzman/services/' 'src/duzman/runtime/' 'src/duzman/api/' 'src/duzman/patterns/' 'src/duzman/collectors/'
```
Ожидается: только `Asset.symbol` (PK таблицы assets) и FK-декларации `ForeignKey("assets.symbol")`. Ни одного `PriceSnapshot.symbol` или `MarketDataSnapshot.symbol`.```
git grep -nE '\.collected_at\b' -- 'src/'
```
Ожидается: пусто.

```
git grep -nE '\.volume_24h_quote\b' -- 'src/'
```
Ожидается: множественные вхождения (поле сохранено как есть, переименование не выполнялось).

```
git grep -nE '\.volume_24h_usd\b' -- 'src/'
```
Ожидается: пусто (этого имени в коде быть не должно).

```
git grep -nE 'PriceSnapshot\.(asset|ts|price_usd)\b' -- 'src/'
```
Ожидается: множественные вхождения в repositories/services/runtime/api/patterns.

```
grep -n "Known schema drift" docs/TZ.md
```
Ожидается: пусто (блок удалён).

```
grep -nE "ts TIMESTAMPTZ|asset VARCHAR.*assets|price_usd NUMERIC|volume_24h_quote NUMERIC|quote_currency VARCHAR" docs/TZ.md
```
Ожидается: 5 строк в обновлённой DDL `price_snapshots`.

```
grep -n "idx_price_ts_asset" docs/TZ.md
```
Ожидается: пусто (старый индекс из DDL удалён).

```
ls src/duzman/db/alembic/versions/ | grep canonicalize
```
Ожидается: один новый файл миграции.

```
.venv/bin/python -m alembic current
```
Ожидается: revision новой миграции на dev DB.

```
.venv/bin/python -c "from sqlalchemy import inspect; from duzman.db.session import sync_engine; cols = [c['name'] for c in inspect(sync_engine).get_columns('price_snapshots')]; assert 'asset' in cols and 'ts' in cols and 'price_usd' in cols and 'volume_24h_quote' in cols; assert 'symbol' not in cols and 'collected_at' not in cols and 'price' not in cols and 'volume_24h_usd' not in cols; print('OK:', sorted(cols))"
```
Ожидается: `OK: [...]` без ошибок.

```
.venv/bin/python -m pytest -q
```
Ожидается: 268 passed.

```
git diff --stat
```
Ожидается: изменения в файлах из «Зоны спецификации», новый файл миграции, ~30 строк удалено из docs/TZ.md.

## Ветка и PR

- Ветка: `techdebt/07-canonicalize-pricesnapshot`
- Заголовок PR: `refactor: canonicalize PriceSnapshot to asset/ts/price_usd (#7)`
- Тело PR заполнить по шаблону. В разделе Issue — `Closes #7`. В отдельном разделе «Preflight» привести вывод трёх preflight-команд с пометками «no external consumers found».
- В Definition of done и Проверки скопировать пункты из этой спеки.

## Forbidden actions

Стандартный набор из Приложения Ж docs/TZ.md. Дополнительно:

- НЕ изменять файлы вне «Зоны спецификации». В частности, НЕ трогать AGENTS.md, SKILL.md, README.md, ARCHITECTURE.md, LOCAL_DEV_SETUP.md, журнал изменений TZ, таблицу версий TZ, другие миграции, модели соседних таблиц.
- НЕ запускать `alembic upgrade` на prod (`/opt/duzman`). Миграция применяется только в dev (`~/duzman`).
- НЕ менять `Asset.symbol` (PK таблицы `assets`).
- НЕ менять `.asset` атрибуты у других моделей (`Indicator`, `FundingRate`, `OpenInterest`, `LongShortRatio`, `Liquidation`, `LiquidationHeatmap`, `PatternTrigger`, `EtfFlow`).
- НЕ выполнять `op.add_column`/`op.drop_column` в новой миграции (только rename).
- НЕ делать data backfill, не запускать SQL `UPDATE` на существующих данных.
- НЕ создавать compatibility-слой (старые имена не должны существовать ни в API, ни в DTO).
- НЕ закрывать Issue #7 в PR-описании, если хотя бы одна проверка из «Проверок» не прошла — в этом случае использовать `Refs #7` и эскалировать Operator-у.
- Если preflight guard выявил внешнего потребителя старых имён — НЕ продолжать выполнение, остановиться и вернуть отчёт.

## Эскалация

Если в процессе работы выявлено:
- Поле, переименование которого ломает > 5 файлов вне зоны спецификации,
- Зависимость в коде, не учтённая в audit,
- Конфликт с другой моделью,
- Любая неоднозначность в применении правил,

— остановиться, откатить локальные изменения, оставить отчёт в коммент к Issue #7 и эскалировать Operator-у через PR-черновик с пометкой `[NEEDS_TZ_UPDATE]` или `[BLOCKED]`.
