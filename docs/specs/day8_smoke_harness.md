# Day 8 Smoke Harness — PR 3c

## Goal

Day 8 smoke harness provides manual, dev-only verification for the Telegram and AI explanation delivery path before feature rollout.

- B0 verifies base Telegram alert delivery without the AI explanation layer.
- B1 verifies AI explanation processing for an existing B0 smoke trigger.
- Both commands are runtime entrypoints, not scheduler jobs.

## Inputs And Outputs

### B0: Telegram Base Smoke

Command:

```bash
.venv/bin/python -m duzman.runtime.verify_telegram_base
```

Inputs:

- Product settings loaded through `Settings`.
- Database connection from `DATABASE_URL`.
- Telegram Bot API credentials from `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID_ALERTS`.

Successful output:

```text
TELEGRAM_BASE_SMOKE_OK telegram_message_id=<id> trigger_id=<id>
```

B0 inserts one synthetic `pattern_triggers` row with:

- `asset = "BTC"`
- `pattern_name = "smoke_b0"`
- `severity = "INFO"`
- `conditions_snapshot.gate_decision = "ALLOW"`
- `alert_sent = true`

Then it runs `TelegramAlertPoller.run_once(..., limit=1)` and verifies that an `alert_deliveries` row exists with `status = "sent"` and a stored `telegram_message_id`.

### B1: AI Explanation Smoke

Command:

```bash
.venv/bin/python -m duzman.runtime.run_ai_explanation_smoke --trigger-id <b0_trigger_id>
```

Optional rollback command:

```bash
.venv/bin/python -m duzman.runtime.run_ai_explanation_smoke --trigger-id <b0_trigger_id> --rollback
```

Inputs:

- A B0 `pattern_triggers.id` passed as `--trigger-id`.
- Product settings loaded through `Settings`.
- AI explanation settings and Anthropic credentials.
- Existing Telegram delivery row for the B0 trigger.

Successful output:

```text
AI_EXPLANATION_SMOKE_OK alert_explanation_id=<id> tokens=<count>
```

With `--rollback`, a successful B1 run also prints:

```text
SMOKE_ROLLBACK_OK pattern_trigger=<label> alert_delivery=<label> alert_explanation=<label>
```

## Exit Codes

Both smoke commands use the same exit-code contract:

- `0`: OK.
- `1`: generic unexpected failure.
- `2`: validation failure, missing settings, missing trigger, wrong trigger, or missing delivery.
- `3`: worker or delivery path did not complete successfully.

B0 returns `3` when Telegram delivery is missing, not marked `sent`, or lacks `telegram_message_id`.

B1 returns `3` when the AI explanation worker leaves the explanation outside successful terminal statuses (`completed` or `reused_cache`) or produces no explanation text.

## Required Environment Variables

B0 requires:

- `DATABASE_URL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID_ALERTS`
- `AI_EXPLANATIONS_ENABLED=false`

B1 requires:

- `DATABASE_URL`
- `ANTHROPIC_API_KEY`
- `AI_EXPLANATIONS_ENABLED=true`

Recommended B1 cost-cap settings for smoke runs:

- `AI_EXPLANATION_MAX_PER_HOUR <= 3`
- `AI_EXPLANATION_MAX_PER_DAY <= 5`

The B1 command logs a warning when configured caps are above those smoke recommendations, but the warning does not block execution.

## Database State Requirements

The smoke harness runs against the configured Duzman database.

- `assets` must contain `BTC`; B0 inserts `pattern_triggers.asset = "BTC"`, which is a foreign key.
- Day 7 and Day 8 migrations must be applied: `alert_deliveries`, `telegram_channel_state`, and `alert_explanations` must exist.
- B1 expects the B0 trigger and its Telegram `alert_deliveries` row to be present unless `--rollback` is used against an already-removed trigger.

## Idempotent Rollback Semantics

Rollback is implemented by B1, not B0.

- `SMOKE_ROLLBACK_OK` means B1 completed successfully and then attempted to delete the smoke chain: `alert_explanations`, `alert_deliveries`, and `pattern_triggers`.
- Each rollback label is row-local and reports whether that row was `deleted` or `missing`.
- `SMOKE_ROLLBACK_NOOP` means `--rollback` was requested but the trigger was already absent; the command treats this as successful idempotent cleanup and exits `0`.

Rollback deletes only rows addressed by the supplied B0 trigger id, its delivery id, and the explanation id created or found during the B1 run.

## Defence In Depth

B1 validates that the supplied trigger belongs to the smoke harness before it creates or processes an explanation:

```text
pattern_name == "smoke_b0"
```

If the trigger exists but has another `pattern_name`, B1 prints `trigger is not a smoke_b0 trigger` and exits with code `2`. This prevents the smoke command from processing or rolling back non-smoke production alerts by accident.
