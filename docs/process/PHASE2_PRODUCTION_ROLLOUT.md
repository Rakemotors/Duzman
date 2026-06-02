# Duzman Phase 2 — Production Rollout Runbook

Version: 1.0
Date: 2026-06-02
Target commit: 53a03dd (Recover stale dispatch rows)
Status: ready for Stage 0–6 execution; Stage 7 requires separate operator decision

---

## Overview

Phase 2 wires Telegram dispatch into the hourly Pattern Engine scheduler.
The code is deployed in two distinct stages:

- **Stages 0–6**: deploy code to `/opt/duzman`, restart scheduler, verify
  stability. Telegram dispatch remains disabled. No Telegram messages are sent.
- **Stage 7**: separate explicit gate to enable real Telegram dispatch by
  setting `TELEGRAM_ENABLED=true` in `.env`. This stage is never part of a
  routine deploy.

Do not combine Stage 7 with a code deploy. They are separate operator actions
with separate verification steps.

---

## Safety invariants

These invariants must hold throughout every stage:

- `.env` is never printed, pasted, or shown in any log or chat.
- `stat -c "%U %G %a" /opt/duzman/.env` must always return `duzman duzman 600`.
- No alembic migration is required for Phase 2. If `alembic current` shows a
  pending migration after deploy, stop and investigate before proceeding.
- `TELEGRAM_ENABLED` defaults to `false`. Stages 0–6 do not change it.

---

## Stage 0 — Pre-deploy repo verification (local)

Run on the local machine before any SSH connection.

    git log --oneline -5
    # HEAD must be 53a03dd

    git status
    # must be clean

    git diff origin/main
    # must be empty

No code edits, no `.env` edits, no alembic commands at this stage.

---

## Stage 1 — VPS pre-deploy snapshot (read-only)

SSH to the VPS. All commands in this stage are read-only.

    systemctl status duzman-scheduler.service --no-pager -l
    # expected: active (running), no recent failures

    systemctl status duzman-health.service --no-pager -l
    # expected: active (running)

    curl -sf http://localhost:8080/health | python3 -m json.tool
    # expected: status ok; record current version and build_sha

    stat -c "%U %G %a" /opt/duzman/.env
    # expected: duzman duzman 600

    ls -la /opt/duzman/
    # confirm expected layout

    cd /opt/duzman && .venv/bin/alembic current
    # record the current revision; Phase 2 requires no new migration

Record: build_sha from /health, alembic revision, service uptime.
Do not `cat` or read `.env` content.

---

## Stage 2 — Deploy

Run from the local Duzman repository directory.

    bash deploy/deploy.sh --dry-run
    # review output carefully:
    # - no .env in sync list
    # - no migration commands
    # - no systemd commands
    # - no unexpected files

    bash deploy/deploy.sh --apply
    # syncs repo tree to /opt/duzman
    # excludes: .git, .venv, .env, caches, logs, backup state

After deploy, verify `.env` was not touched:

    stat -c "%U %G %a" /opt/duzman/.env
    # must still be: duzman duzman 600

Verify alembic state did not drift:

    cd /opt/duzman && .venv/bin/alembic current
    # must match the pre-deploy revision exactly

Spot-check one Phase 2 file landed correctly:

    diff <(cd /home/operator/Duzman && git show HEAD:src/duzman/dispatch/runtime.py) \
         /opt/duzman/src/duzman/dispatch/runtime.py
    # must produce no output

---

## Stage 3 — Service restart

Restart only the scheduler service. The health service does not need restart
because no health endpoint changes were made in Phase 2.

    systemctl restart duzman-scheduler.service

    sleep 5 && systemctl status duzman-scheduler.service --no-pager -l
    # expected: active (running), no crash on startup

    curl -sf http://localhost:8080/health | python3 -m json.tool
    # expected: status ok
    # expected: build_sha updated to 53a03dd if BUILD_SHA file is populated

---

## Stage 4 — Log verification (first 60 seconds after restart)

    journalctl -u duzman-scheduler.service -n 80 --no-pager

Scan output for the following:

Must NOT appear:
- `ERROR`, `CRITICAL`, `Traceback`
- Any secret string (token, key, password, chat id value)
- `dispatch_runtime_disabled` — would indicate telegram_enabled=true leak
- `dispatch_stale_sending_recovered` — would indicate unexpected sending rows

Must appear:
- Scheduler started log line
- Jobs registered log lines

Additional targeted check for dispatch-related lines:

    journalctl -u duzman-scheduler.service -n 80 --no-pager \
        | grep -i "telegram\|anthropic\|dispatch" || true
    # expected: no output (dispatch is disabled, no dispatch log events expected)

---

## Stage 5 — First post-deploy scheduler tick

The pattern tick job runs at XX:33 UTC. Wait for it, then check logs.

    journalctl -u duzman-scheduler.service --since "10 minutes ago" --no-pager

Expected in logs after tick:
- `pattern_tick_cycle_completed` with `allowed_count` and `elapsed_ms`

Must NOT appear:
- `dispatch_runtime_disabled` (only emitted when enabled=True but somehow skipped)
- `dispatch_stale_sending_recovered`
- Any `ERROR` or `Traceback`

Verify no stale or active sending rows in the database:

    cd /opt/duzman && .venv/bin/python -c "
    import asyncio
    from duzman.db.session_async import build_async_database_session_components
    from duzman.settings import settings
    from sqlalchemy import text

    async def check():
        c = build_async_database_session_components(settings)
        async with c.session_factory() as s:
            r = await s.execute(text(
                \"SELECT COUNT(*) FROM alert_deliveries WHERE status = 'sending'\"
            ))
            print('sending rows:', r.scalar())
            r2 = await s.execute(text(
                \"SELECT COUNT(*) FROM alert_deliveries WHERE status = 'failed' \"
                \"AND error_message = 'stale_sending_delivery_recovered'\"
            ))
            print('stale-recovered rows:', r2.scalar())
        await c.engine.dispose()

    asyncio.run(check())
    "
    # sending rows: must be 0
    # stale-recovered rows: 0 expected on first deploy (no prior dispatch)

---

## Stage 6 — Deploy verification gate

Before any dispatch enablement, all of the following must be confirmed:

    [ ] systemctl status duzman-scheduler.service  →  active (running)
    [ ] systemctl status duzman-health.service     →  active (running)
    [ ] /health                                    →  status ok, build_sha = 53a03dd
    [ ] alembic current                            →  same revision as pre-deploy
    [ ] .env stat                                  →  duzman duzman 600, not modified
    [ ] pattern_tick_cycle_completed in logs       →  present after deploy
    [ ] logs scan                                  →  no ERROR, Traceback, secret values
    [ ] sending rows in DB                         →  0
    [ ] no unexpected alert_deliveries rows        →  confirmed

If all items pass: code deploy is stable. Proceed to Stage 7 at a separate
operator decision point, not immediately.

If any item fails: stop. Do not proceed to Stage 7. Investigate and resolve
before re-attempting.

---

## Stage 7 — Telegram dispatch enablement (separate explicit gate)

Stage 7 is not part of a routine code deploy. It requires a separate
operator decision after Stage 6 has passed and at least one clean hourly
tick has been observed post-deploy.

### Pre-conditions before Stage 7

- Stage 6 gate fully passed.
- At least one `pattern_tick_cycle_completed` observed in production logs
  after the Stage 3 restart.
- No sending rows in `alert_deliveries`.
- No unexplained errors in scheduler logs since Stage 3.
- Operator has confirmed `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are
  present and correct in `/opt/duzman/.env`.

### Enablement steps

Edit `.env` on the VPS only — not in git, not in any chat:

    # Change in /opt/duzman/.env:
    # TELEGRAM_ENABLED=false  →  TELEGRAM_ENABLED=true

After edit, verify `.env` mode was not changed:

    stat -c "%U %G %a" /opt/duzman/.env
    # must still be: duzman duzman 600

Restart only the scheduler:

    systemctl restart duzman-scheduler.service

    sleep 5 && systemctl status duzman-scheduler.service --no-pager -l
    # expected: active (running)

### Observing the first enabled tick

Wait for the next pattern tick at XX:33 UTC, then watch logs:

    journalctl -u duzman-scheduler.service --since "2 minutes ago" -f

Expected events to watch for:

| Log event | Meaning | Action |
|---|---|---|
| `pattern_tick_cycle_completed` | tick ran normally | good |
| `dispatch_delivery_duplicate_skipped` | idempotency working | expected if re-ticking known triggers |
| `dispatch_stale_sending_recovered` | stale rows found and recovered | warning — investigate how rows became stale |
| `dispatch_runtime_disabled` | telegram_enabled still false | check .env, restart did not pick up change |
| `ERROR` or `Traceback` | something failed | stop, investigate |

After first enabled tick, verify delivery rows:

    cd /opt/duzman && .venv/bin/python -c "
    import asyncio
    from duzman.db.session_async import build_async_database_session_components
    from duzman.settings import settings
    from sqlalchemy import text

    async def check():
        c = build_async_database_session_components(settings)
        async with c.session_factory() as s:
            r = await s.execute(text(
                \"SELECT status, COUNT(*) FROM alert_deliveries \"
                \"GROUP BY status ORDER BY status\"
            ))
            for row in r:
                print(row[0], row[1])
        await c.engine.dispose()

    asyncio.run(check())
    "
    # expected: rows with status=sent or status=skipped_disabled
    # sending rows: must be 0 after tick completes

### Rollback

Telegram dispatch can be disabled without a code deploy:

    # In /opt/duzman/.env:
    # TELEGRAM_ENABLED=true  →  TELEGRAM_ENABLED=false

    systemctl restart duzman-scheduler.service

    # Verify no dispatch activity in next tick logs

No migration or code change is needed to roll back dispatch enablement.

---

## Stale sending row reference

If `dispatch_stale_sending_recovered` appears in logs, rows were found in
`status=sending` with `updated_at` older than the configured
`stale_sending_timeout_minutes` (default: 10 minutes). These rows have been
marked `failed` with `error_message=stale_sending_delivery_recovered`.

This means a previous tick reserved a delivery but crashed before finalizing.
The alert was not sent. The idempotency row is preserved, so no duplicate send
will occur automatically.

To investigate and optionally retry a stale-recovered delivery, an explicit
operator action is required. No automatic resend mechanism exists in Phase 2.

Query stale-recovered rows:

    SELECT id, alert_id, channel, status, error_message, updated_at
    FROM alert_deliveries
    WHERE error_message = 'stale_sending_delivery_recovered'
    ORDER BY updated_at DESC;

Any resend decision must be a separate operator-approved workflow.
