# Phase 2 Spec 4 — AI Explanation Worker For Dispatch Flow

Version: 1.0
Status: implemented
Based on: Техническое задание v1.10 от 2026-05-25 (docs/TZ.md)
Reference: GitHub Issue #103

## 1. Context And Goal

Phase 2 Spec 4 adds an inert dispatch-facing AI explanation worker abstraction.
It lets future dispatch flow code request an explanation for a `DispatchEvent`
through injected provider dependencies while keeping provider calls fakeable and
deterministic in tests.

This spec does not wire AI explanations into scheduler, runtime, Telegram
delivery, AlertGate, Pattern Engine, production database sessions, or
deployment.

## 2. Scope

In scope:

- `src/duzman/dispatch/ai_worker.py`
- `DispatchAIExplanationWorker`, an async worker that accepts one
  `DispatchEvent` and returns a bounded result object.
- `DispatchExplanationGenerator`, a provider protocol implemented by injected
  fakes or future external provider adapters.
- `DispatchExplanationCache`, an optional injected cache protocol that avoids
  duplicate provider calls for identical dispatch explanation requests.
- Deterministic request building from `DispatchEvent` into system prompt, user
  prompt, prompt hash, cache key, and JSON-safe prompt context.
- Offline dispatch tests with fake generator and fake cache dependencies.

Out of scope:

- Anthropic client construction.
- Settings or `.env` reads.
- `DATABASE_URL` or live database use.
- Scheduler/runtime wiring.
- Telegram reply sending.
- Alembic migrations.
- Production deployment or `/opt/duzman` changes.

## 3. Contracts

`DispatchAIExplanationWorker.explain(event)` returns
`DispatchAIExplanationResult`.

Statuses:

- `completed`: provider generated non-empty explanation text.
- `failed`: provider raised a safe failure, generic provider exception occurred,
  or provider returned blank text.
- `skipped_disabled`: worker is disabled, so no cache or provider dependency is
  called.
- `reused_cache`: injected cache returned an existing explanation for the
  deterministic cache key.

Retryable terminal statuses remain aligned with the Day 8 AI explanation
semantics:

- `failed`
- `failed_stale`
- `skipped_cost_cap`

Spec 4 does not persist these statuses. It exposes the taxonomy for future
dispatch composition without changing the existing Day 8 DB-backed worker.

## 4. Determinism

The request builder uses only `DispatchEvent` fields and the existing Day 8
system prompt text. It never calls `datetime.now()`.

The cache key is derived from asset, pattern name, severity, gate decision, and
matched condition names. This mirrors the existing Day 8 cache reason model
without importing runtime composition or creating database rows.

Provider exception messages are not copied into results unless the injected
provider raises `DispatchExplanationProviderError` with an explicit safe
reason. Generic exceptions map to their class name.

## 5. Boundary

The dispatch AI worker is production-facing code, but it is inert until a
future runtime spec composes it with real dependencies. It does not import from
the Spec 6 harness and the harness does not become a production dependency.

Tests do not construct Anthropic clients, read secrets, read settings, use
`DATABASE_URL`, or make network calls.

## 6. Future Work

Future Spec 5 runtime composition can adapt this worker to a concrete provider,
persistence, and Telegram reply path. That future work must still own runtime
error handling, database session lifecycle, budget enforcement, and production
configuration boundaries explicitly.
