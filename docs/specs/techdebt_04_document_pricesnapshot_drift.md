# techdebt_04: фиксация PriceSnapshot schema drift в TZ

Based on: Техническое задание v1.7 от 2026-05-19 (docs/TZ.md)

## Issue

Refs #7

Закрытие #7 откладывается до следующей задачи (audit + миграция C). Эта спека фиксирует дрейф документально, чтобы дальнейшие решения принимались на основе явно отражённого факта в TZ.

## Контекст

В коде модель `PriceSnapshot` (`src/duzman/db/models.py`) и соответствующая таблица `price_snapshots` фактически имеют схему, отличающуюся от DDL в Приложении Б docs/TZ.md.

В TZ DDL:
- `ts TIMESTAMPTZ`
- `asset VARCHAR(10)` (FK на `assets.symbol`)
- `price_usd NUMERIC(20,8)`
- `volume_24h_usd NUMERIC(20,2)`
- `price_change_24h_pct NUMERIC(8,4)`
- `price_change_7d_pct NUMERIC(8,4)`
- `source VARCHAR(20)`

В коде (после миграции `2b8f4f6c9a1e_normalize_price_snapshots`, применена 2026-05-15):
- `collected_at TIMESTAMPTZ NOT NULL`
- `symbol VARCHAR(10) NOT NULL` (FK на `assets.symbol`)
- `price NUMERIC(20,8) NOT NULL`
- `volume_24h_quote NUMERIC(20,2) NULL`
- `price_change_24h_pct NUMERIC(8,4) NULL`
- `source VARCHAR(20) NOT NULL`
- `quote_currency VARCHAR(10) NOT NULL` (добавлено)
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` (добавлено)
- `raw_payload JSON NULL` (добавлено)
- `price_change_7d_pct` (удалено)

Соседние таблицы (`indicators`, `funding_rates`, `open_interest`, `liquidations`, `etf_flows`, `global_metrics`) и в TZ, и в коде используют `asset/ts`. PriceSnapshot — единственный outlier.

Решение: НЕ менять код и не откатывать миграцию в рамках этой задачи. Зафиксировать дрейф в TZ как known schema drift. Решение о канонической схеме (вариант C: переименовать `symbol/collected_at/price → asset/ts/price_usd` с сохранением `quote_currency/created_at/raw_payload`) принимается отдельной задачей после audit.

## Зона спецификации

- docs/TZ.md

Файлы вне этого списка изменяться не должны. Код, миграции, тесты, AGENTS.md, SKILL.md в эту задачу НЕ входят.

## Что нужно сделать

В docs/TZ.md в Приложении Б, непосредственно после блока DDL для `price_snapshots` (после строки `CREATE INDEX idx_price_ts_asset ON price_snapshots(ts DESC, asset);`), вставить новый блок-предупреждение следующего содержания (дословно):

```
> Known schema drift (PriceSnapshot, на 19.05.2026)
>
> Фактическая схема таблицы `price_snapshots` в коде и в применённой
> миграции `2b8f4f6c9a1e_normalize_price_snapshots` отличается от
> приведённой выше DDL:
>
> - `ts` → `collected_at`
> - `asset` → `symbol` (FK на `assets.symbol` сохранён)
> - `price_usd` → `price` (NOT NULL)
> - `volume_24h_usd` → `volume_24h_quote`
> - удалено: `price_change_7d_pct`
> - добавлены: `quote_currency VARCHAR(10) NOT NULL`,
>   `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`,
>   `raw_payload JSON NULL`
> - индексы: `ix_price_snapshots_source_symbol_collected_at`,
>   `ix_price_snapshots_collected_at`,
>   `ix_price_snapshots_source` (вместо `idx_price_ts_asset`)
>
> Дрейф введён осознанно миграцией от 2026-05-15. Остальные таблицы
> Приложения Б (`indicators`, `funding_rates`, `open_interest`,
> `liquidations`, `etf_flows`, `global_metrics`) используют именование
> `asset/ts` и совпадают с DDL.
>
> Канонизация схемы (выравнивание имён под проектный стандарт
> `asset/ts/price_usd` с сохранением дополнительных полей) решается
> отдельной задачей после audit использования полей. Источник правды
> для разработки на текущий момент — код и миграция, не DDL выше.
```

Других изменений в TZ не делать. Журнал изменений в шапке TZ и таблицу версий внизу TZ — не трогать (это PATCH-уровневая фиксация факта, не контракта).

## Definition of done

- [ ] В docs/TZ.md в Приложении Б после строки `CREATE INDEX idx_price_ts_asset ON price_snapshots(ts DESC, asset);` присутствует блок `> Known schema drift (PriceSnapshot, на 19.05.2026)` ровно с тем содержанием, что указано выше.
- [ ] DDL-блок `CREATE TABLE price_snapshots (...)` не изменён.
- [ ] DDL других таблиц в Приложении Б не изменены.
- [ ] Журнал изменений в шапке TZ не изменён.
- [ ] Таблица версий внизу TZ не изменена.
- [ ] Никакие другие файлы PR не трогает.
- [ ] Тесты зелёные: `.venv/bin/python -m pytest -q`.

## Проверки

```
grep -n "Known schema drift (PriceSnapshot" docs/TZ.md
```
Ожидается: ровно одна строка.

```
grep -n "CREATE TABLE price_snapshots" docs/TZ.md
```
Ожидается: одна строка, как и до правки.

```
grep -n "idx_price_ts_asset" docs/TZ.md
```
Ожидается: одна строка с прежним `CREATE INDEX idx_price_ts_asset ON price_snapshots(ts DESC, asset);`.

```
grep -nE "ts → collected_at|asset → symbol|price_usd → price" docs/TZ.md
```
Ожидается: три строки (все три переименования упомянуты).

```
git diff --stat
```
Ожидается: изменён только docs/TZ.md, прирост строк около 25–30.

```
.venv/bin/python -m pytest -q
```
Ожидается: 268 passed.

## Ветка и PR

- Ветка: `techdebt/07-document-pricesnapshot-drift`
- Заголовок PR: `docs: document PriceSnapshot schema drift in TZ Appendix B (refs #7)`
- Тело PR: заполнить по шаблону. В разделе Issue написать `Refs #7` (НЕ `Closes #7` — Issue остаётся открытым до канонизации схемы).
- В Definition of done и Проверки скопировать пункты из этой спеки.

## Forbidden actions

Стандартный набор из Приложения Ж docs/TZ.md. Дополнительно:
- НЕ менять DDL в Приложении Б.
- НЕ менять журнал изменений и таблицу версий TZ.
- НЕ менять код в `src/`, тесты в `tests/`, миграции в `src/duzman/db/alembic/versions/`.
- НЕ менять AGENTS.md, .claude/skills/duzman-conventions/SKILL.md, README.md, ARCHITECTURE.md.
- НЕ использовать `Closes #7` в теле PR.
