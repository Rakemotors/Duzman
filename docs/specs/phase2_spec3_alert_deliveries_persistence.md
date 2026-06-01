# Phase 2 Spec 3 — Alert Deliveries Persistence

Version: 1.0
Status: implemented
Based on: Техническое задание v1.10 от 2026-05-25 (docs/TZ.md)
Reference: GitHub Issue #98

## 1. Context And Goal

Phase 2 Spec 3 adds the dispatch-domain persistence boundary for recording
Telegram delivery outcomes in the existing `alert_deliveries` table. It consumes
the Spec 1 `DispatchEvent` contract and Spec 2 `TelegramSendResult` contract,
but remains inert: no scheduler wiring, no AlertGate changes, no runtime
entrypoint, no Telegram calls, no AI worker, and no production deployment.

The goal is to provide an idempotent repository that future Spec 5 orchestration
can call after a Telegram send attempt.

## 2. Scope

In scope:

- `AlertDeliveryRow`, an immutable dispatch-domain row contract.
- `RecordDeliveryResult`, an immutable idempotent insert result.
- `delivery_row_from_telegram_result()`, a pure mapping from Spec 1 and Spec 2
  values into persistence row data.
- `DispatchDeliveryRepository`, a session-scoped async repository that records,
  looks up, and acknowledges delivery rows.
- Offline async SQLite tests for row validation, mapping, idempotent inserts,
  conflicts, lookups, acknowledgement updates, and concurrent insert races.

Out of scope:

- New ORM models or migrations.
- Changes to existing DB models or DB repositories.
- Scheduler/runtime wiring.
- AlertGate, Pattern Engine, AI, Telegram send execution, or production deploy.

## 3. Existing Schema And ORM Decision

No migration is required. The existing ORM model is reused:

- Path: `src/duzman/db/models.py`
- Class: `AlertDelivery`
- Table: `alert_deliveries`

The existing historical repository also remains in place:

- `src/duzman/db/repositories/alert_deliveries.py::AlertDeliveryRepository`

Spec 3 adds a new dispatch-domain repository instead of changing that legacy
repository, so the current Day 7 Telegram runtime behavior is not affected.

## 4. Naming Drift

The database column `alert_deliveries.alert_id` semantically references
`pattern_triggers.id`. Dispatch-domain code uses the clearer Python name
`pattern_trigger_id`.

`DispatchDeliveryRepository` performs the mapping:

```text
AlertDeliveryRow.pattern_trigger_id -> AlertDelivery.alert_id
```

The idempotency boundary remains the existing unique constraint on
`(alert_id, channel)`.

## 5. Repository Contract

`DispatchDeliveryRepository` accepts an `AsyncSession` at construction time.
Callers own transaction commit/rollback, session lifecycle, and async engine
disposal.

Public methods:

- `record_delivery(row)`: dialect-aware `INSERT ... ON CONFLICT DO NOTHING
  RETURNING id`, followed by a secondary lookup when the row already exists.
- `find_existing(pattern_trigger_id, channel)`: returns an `AlertDeliveryRow`
  or `None`.
- `mark_acknowledged(row_id, ack_at)`: updates `ack_at` and `updated_at` to a
  caller-supplied timezone-aware timestamp.

Supported dialects for idempotent insert are PostgreSQL and SQLite. Unsupported
dialects raise `NotImplementedError`.

## 6. Status Mapping

Spec 3 delivery statuses intentionally match Spec 2 Telegram result statuses:

- `sent`
- `failed`
- `skipped_disabled`

`delivery_row_from_telegram_result()` maps:

- `sent`: copies `telegram_message_id` and sets `sent_at` to caller-supplied
  `now`.
- `failed`: stores the bounded `error_reason` in `error_message` and leaves
  `sent_at` unset.
- `skipped_disabled`: records the skipped status without send fields.

The mapping is pure and does not call `datetime.now()`.

## 7. Test Strategy

Tests use `sqlite+aiosqlite:///:memory:` and create a minimal schema for
`assets`, `pattern_triggers`, and `alert_deliveries`. They do not require
`DATABASE_URL`, do not run migrations, and do not touch a live database.

The tests reuse the repository style already present in
`tests/db/test_pattern_trigger_repository.py`: async SQLite engine, explicit DDL,
`async_sessionmaker(..., expire_on_commit=False)`, and fixture-owned engine
disposal.

## 8. Future Tightening

Production concurrency is enforced by the existing unique constraint and
PostgreSQL `ON CONFLICT`. SQLite tests exercise the same repository branch with
SQLite's dialect-specific insert helper, but PostgreSQL remains the production
source of truth.

Future Spec 5 wiring should compose this repository with the Spec 1 dispatcher
contract and Spec 2 Telegram sender. It should not move transaction ownership
into the repository unless the runtime composition boundary changes explicitly.
