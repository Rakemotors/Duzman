# Phase 2 Spec 6 — Deterministic Dispatch Harness

Version: 1.0
Status: implemented
Based on: Техническое задание v1.10 от 2026-05-25 (docs/TZ.md)
Reference: GitHub Issue #101

## 1. Context And Goal

Phase 2 Spec 6 adds a deterministic offline dispatch harness that composes the
existing dispatch contract, Telegram send result contract, and dispatch
persistence repository without wiring scheduler, runtime, Pattern Engine,
Telegram network, or AI runtime code.

The goal is to exercise dispatch orchestration behavior in tests with real
idempotent `alert_deliveries` persistence and fake deterministic sender and AI
dependencies.

## 2. Scope

In scope:

- `FakeTelegramSender`, an async sender fake that records `DispatchEvent` calls
  and returns configured or deterministic default `TelegramSendResult` values.
- `FakeAIWorker`, an async explanation fake that records calls and returns a
  deterministic explanation string.
- `FakePersistence`, an async context manager that owns an in-memory
  `sqlite+aiosqlite:///:memory:` engine, creates a minimal schema, seeds BTC
  trigger ids 1, 2, and 3, and uses the real `DispatchDeliveryRepository`.
- `DispatchHarness`, `HarnessDispatchResult`, and `run_dispatch_harness()` for
  sequential batch processing.
- Offline async tests under `tests/dispatch/harness/`.

Out of scope:

- Scheduler or runtime wiring.
- AlertGate, Pattern Engine, market-data, AI runtime, or Telegram runtime
  changes.
- New migrations, settings changes, production database access, or deployment.
- Real Telegram, Anthropic, or other network calls.

## 3. Harness Contract

`run_dispatch_harness(harness, events, now)` processes input events in order.
For each event it:

- calls `FakeTelegramSender.send(event)`;
- calls `FakeAIWorker.explain(event)`;
- maps the Telegram result with `delivery_row_from_telegram_result()`;
- records the row through `DispatchDeliveryRepository.record_delivery()`;
- returns a `HarnessDispatchResult` containing the event, Telegram result,
  explanation, and record result.

Sender exceptions are not caught by the harness. Runtime error handling remains
outside this spec.

## 4. Determinism

The default fake sender outcome is `status="sent"` with
`telegram_message_id = pattern_trigger_id * 100`. The default fake AI
explanation is `fake explanation`.

The harness never calls `datetime.now()`. Tests and callers supply the
timezone-aware `now` value used by the persistence mapping.

## 5. Persistence Model

`FakePersistence` creates only the minimal tables required by the existing
dispatch persistence repository:

- `assets`
- `pattern_triggers`
- `alert_deliveries`

The seeded asset is BTC. The seeded pattern trigger ids are 1, 2, and 3. This
keeps tests offline and avoids `DATABASE_URL`, Alembic, production DB access,
or environment-dependent setup.

## 6. Test Strategy

Spec 6 tests verify:

- sent events persist sent rows;
- failed events persist failed rows;
- skipped-disabled events persist skipped rows;
- duplicate events are idempotent through `(alert_id, channel)`;
- multi-event batches return all results in order;
- fake AI worker and fake sender call counts match input events;
- returned harness results carry the explanation string.

## 7. Boundary

The harness package does not import from runtime, scheduler, AI runtime,
Pattern Engine, Telegram runtime, or database settings. It is a deterministic
test composition layer for future dispatch work only.

## 8. Future Tightening

Future runtime specs can use this harness as a regression fixture for
orchestration semantics, but production dispatch wiring should remain separate
and continue to own runtime error handling, database session composition, and
external sender configuration.
