# Phase 2 Spec 5 — Dispatch Runtime Wiring

Version: 1.0
Status: implemented
Based on: Техническое задание v1.10 от 2026-05-25 (docs/TZ.md)
Reference: GitHub Issue #106

## 1. Context And Goal

Phase 2 Spec 5 wires the existing dispatch components into the hourly Pattern
Engine scheduler path with explicit safety gates. This is a PR-only runtime
wiring change: no production execution, deployment, systemd change, database
migration, or post-merge verification is part of this spec.

The goal is to dispatch committed AlertGate `ALLOW` pattern trigger rows through
the Phase 2 Telegram sender and dispatch delivery persistence, while keeping
production activation disabled unless Telegram dispatch is explicitly enabled
through existing settings.

## 2. Scope

In scope:

- `DispatchRuntimeService`, a small runtime composition service that reserves a
  Telegram delivery row before sending and finalizes it after the send result.
- Scheduler dispatch event construction from persisted `pattern_triggers` rows
  for the current tick.
- Runtime scheduler composition that builds the dispatch service only when
  `telegram_enabled` is true.
- Explicit `dialect="postgresql"` dispatch persistence configuration in runtime
  composition.
- Offline tests with fake Telegram sender and fake AI worker dependencies.

Out of scope:

- Production deployment or `/opt/duzman` access.
- Alembic migrations or schema changes.
- Systemd changes or scheduler execution in production.
- Real Telegram or Anthropic calls in tests.
- Pattern Engine or AlertGate behavior changes.

## 3. Enablement

Runtime dispatch is disabled by default because `telegram_enabled` defaults to
`False`. When disabled, the scheduler still runs the Pattern Engine tick and
persists AlertGate decisions, but no dispatch service is constructed and no
Telegram or AI call is made.

When enabled, runtime composition builds:

- `TelegramHttpClient`
- `TelegramBaseSender`
- `DispatchRuntimeService`

The service is constructed with `dialect="postgresql"` for
`DispatchDeliveryRepository` creation. Tests inject fakes and use
`dialect="sqlite"`.

## 4. Idempotency

`DispatchRuntimeService` prevents duplicate sends by reserving the
`(pattern_trigger_id, telegram)` idempotency key before calling Telegram:

1. Insert `alert_deliveries` row with status `sending`.
2. If the insert conflicts, skip send and AI work.
3. If inserted, call the Telegram sender.
4. Finalize the same row as `sent`, `failed`, or `skipped_disabled`.

This uses the existing unique constraint on `(alert_id, channel)` and does not
require a migration.

## 5. Stale Sending Recovery

Issue #108 adds deterministic recovery for rows that remain
`alert_deliveries.status = "sending"` after a crash between reservation and
finalization.

The implemented policy is conservative:

- `DispatchDeliveryRepository.recover_stale_sending_deliveries()` accepts an
  explicit timezone-aware cutoff timestamp.
- Matching Telegram delivery rows with `status = "sending"` and
  `updated_at < cutoff` are marked `failed`.
- The fixed `error_message` is `stale_sending_delivery_recovered`.
- The existing `(alert_id, channel)` idempotency row is preserved.
- No automatic retry or duplicate Telegram send is attempted.

`DispatchRuntimeService` runs this recovery once before an enabled dispatch
batch. The batch cutoff is derived from the earliest event timestamp minus the
configured stale-sending timeout, so tests can inject deterministic event times
and explicit cutoffs. When recovery updates rows, the runtime emits the warning
event `dispatch_stale_sending_recovered` with only a recovered-row count.

This means a later scheduler tick no longer leaves stale `sending` rows hidden
forever: they become terminal failed rows visible to operators, while duplicate
send risk remains bounded by the existing idempotency constraint.

Production rollout must verify there are no unrecovered stale sending rows
before enabling Telegram dispatch. Any decision to retry a failed stale delivery
must be an explicit operator action or a future approved change; this PR does
not implement automatic resend.

## 6. AI Behavior

Spec 5 accepts an optional injected dispatch AI worker but does not construct a
real Anthropic provider in runtime scheduler composition. This keeps production
AI dispatch inactive in this wiring PR.

The Spec 4 dependency on the Day 8 `SYSTEM_PROMPT` remains contained in
`src/duzman/dispatch/ai_worker.py`; Spec 5 does not expand that dependency or
use it for production provider construction.

AI and cache failures are contained after Telegram delivery persistence. If an
injected AI worker raises, runtime dispatch logs a bounded failure event and
does not roll back or fail the Telegram delivery.

## 7. Safety

Tests use fake senders, fake AI workers, and in-memory SQLite. They do not read
production configuration files, use production database connection settings,
construct real Telegram network transports during sends, construct external AI
clients, or execute production scheduler/runtime.

No deploy scripts, systemd files, migrations, or production paths are changed.

## 8. Future Work

Future production rollout must be a separate operator-approved plan after PR
review and merge. If AI explanations are to be included in dispatch runtime,
that future work must explicitly compose a provider, budget/cost behavior,
cache persistence, and Telegram reply behavior.
