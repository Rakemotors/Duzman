# Phase 2 Spec 1 — Dispatch Event Contract

Version: 1.0
Status: implemented
Based on: Техническое задание v1.10 от 2026-05-25 (docs/TZ.md)
Reference: GitHub Issue #91

## 1. Context And Goal

Phase 2 Spec 1 introduces the pure dispatch domain contract that later runtime
delivery code can consume. This spec intentionally adds data structures only:
no scheduler integration, no AlertGate changes, no Pattern Engine changes, no
database session usage, no Telegram calls, no Anthropic calls, and no network or
async runtime execution.

The contract provides a stable boundary between persisted Pattern Engine
triggers and future dispatch implementations.

## 2. Scope

In scope:

- `DispatchEvent`, the immutable event passed into dispatch implementations.
- `DispatchResult`, the immutable status summary returned by dispatch
  implementations.
- `Dispatcher`, a structural async protocol for future implementations.
- `build_dispatch_event()`, a primitive-only factory that validates the event
  shape without importing DB models.

Out of scope:

- Reading `pattern_triggers` from a database.
- Writing `alert_deliveries` or `alert_explanations`.
- Starting workers or scheduling jobs.
- Sending Telegram messages.
- Creating Anthropic explanation tasks.
- Changing existing hourly runtime wiring.

## 3. Contract

`DispatchEvent` fields:

- `pattern_trigger_id`: positive `pattern_triggers.id` value. This is the
  dispatch idempotency anchor.
- `asset`: asset symbol carried from the matched trigger.
- `pattern_name`: stable Pattern Engine pattern name.
- `severity`: severity label from the matched pattern.
- `ts`: timezone-aware trigger timestamp.
- `conditions_snapshot`: optional matched-condition snapshot captured by the
  Pattern Engine.

`DispatchResult` fields:

- `telegram_status`: status produced by Telegram/base-alert dispatch.
- `explanation_status`: status produced by optional explanation dispatch.
- `errors`: immutable tuple of bounded error messages. It is a
  `tuple[str, ...]`, not a list, so the frozen dataclass remains immutable at
  the container boundary.

`Dispatcher` is a `typing.Protocol` with one method:

```python
async def dispatch(self, event: DispatchEvent) -> DispatchResult: ...
```

The protocol declares the future shape only. This spec does not provide a
runtime implementation.

## 4. Validation And Immutability

Both `DispatchEvent` and `DispatchResult` are frozen dataclasses.

`DispatchEvent` validates the required event fields at construction:

- `pattern_trigger_id > 0`
- `asset` is a non-empty string
- `pattern_name` is a non-empty string
- `severity` is a non-empty string
- `ts` is timezone-aware

Naive datetimes are rejected with:

```text
ValueError("ts must be timezone-aware")
```

`build_dispatch_event()` accepts primitive keyword-only values and applies the
same validation:

- `pattern_trigger_id > 0`
- `asset` is a non-empty string
- `pattern_name` is a non-empty string
- `severity` is a non-empty string
- `ts` is timezone-aware

The builder performs no DB model import and no persistence lookup. It returns a
`DispatchEvent` after validation.

## 5. Idempotency Anchor

The canonical dispatch idempotency anchor is `pattern_triggers.id`, represented
in Python as `pattern_trigger_id`.

Future dispatch persistence should use this id to avoid duplicate delivery for
the same Pattern Engine trigger. This spec does not add that persistence logic;
it only names and validates the value that future implementations will use.

## 6. Historical Naming Drift

The existing `alert_deliveries.alert_id` database column is historical naming
drift from the earlier alert-delivery layer. Semantically, that column maps to
`pattern_triggers.id`.

New Python domain code should use `pattern_trigger_id` for clarity. When future
dispatch code reads or writes `alert_deliveries.alert_id`, it should treat that
column as the persisted reference to `pattern_triggers.id`.

## 7. Future Tightening

`DispatchResult.telegram_status` and `DispatchResult.explanation_status` are
arbitrary strings in Spec 1. Later specs may tighten them to `Literal[...]` or
an enum after Spec 2 and Spec 4 reveal the full status taxonomy.

`conditions_snapshot` is shallow-immutable only because it remains
`dict | None`; the frozen dataclass prevents replacing the attribute, but it
does not deep-freeze nested dictionary contents. Future deep immutability can be
added via a wrapper or helper if later dispatch code needs that guarantee.
