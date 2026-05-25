# Codex Issue Dispatcher Research

Status: research recommendation
Date: 2026-05-25
Related issue: #31
Decision: postpone full automation until explicit operator approval gates, runner safety, and audit controls are implemented.

## Executive Summary

Level 1 is the current manual workflow: an approved GitHub Issue is reviewed by Operator, Operator gives the prompt to Codex CLI on the VPS, Codex edits and verifies inside the repository, review happens through PR, and Operator remains responsible for merge and production rollout.

Level 2 would automate the middle of that flow: GitHub Issue -> Codex CLI run -> branch/PR creation, without manual prompt-copying by Operator.

Recommendation: do not build full Level 2 automation immediately. Build it later only as a separate implementation issue after Operator accepts the safety gates described here. The first implementation should be dry-run only.

## Codex CLI Capability Findings

Observed CLI version:

```text
codex-cli 0.133.0
```

Observed capabilities:

- `codex` has a non-interactive `exec` command.
- `codex exec` accepts an initial prompt as an argv argument.
- `codex exec` reads the prompt from stdin when no prompt argument is provided or when `-` is used.
- `codex exec --json` emits JSONL events to stdout.
- `codex exec --output-last-message <file>` writes the final assistant message to a file.
- `codex exec --cd <dir>` sets the working directory.
- `codex exec --sandbox <mode>` supports sandbox selection, including `workspace-write` and `danger-full-access`.
- `codex exec --ask-for-approval never` is available for non-interactive runs.

Project-local Codex config currently uses:

- `sandbox_mode = "workspace-write"`
- `approval_policy = "on-failure"`
- network enabled for workspace-write sandbox
- secret-like environment names excluded from subprocess inheritance, including key/token/password/credential patterns and project API/database variables

Known limitation in this VPS workflow: Codex can edit project files and run local verification, but the documented sandbox setup has `.git` mounted read-only. Therefore a dispatcher wrapper or Operator must own branch creation, staging, commits, pushes, and PR creation outside the Codex sandbox. Codex should not be expected to create branches or push from inside the sandbox.

## Option Comparison

### Option A - VPS Watcher

A systemd service or cron job on the VPS polls GitHub Issues through `gh`, filters Issues labeled `codex-ready` and `approved-by-operator`, creates an issue-specific branch outside Codex, runs `codex exec`, captures logs, commits/pushes/opens a PR outside Codex, comments the result back to the Issue, and stores state in `.agents/codex-dispatcher/` as JSON or local SQLite.

Pros:

- Uses the existing VPS environment and checked-out repository.
- Avoids replicating Duzman setup on a GitHub-hosted runner.
- Can reuse installed `gh`, Codex auth, virtualenv, and local verification commands.
- Keeps product runtime code untouched.

Cons:

- Risky if prompt approval, lock handling, and audit controls are weak.
- A compromised or poorly reviewed Issue body becomes the Codex prompt.
- Requires careful separation between wrapper-owned git operations and Codex-owned file edits.
- Requires local state cleanup and log retention policy.

### Option B - GitHub Action

A GitHub Action is triggered by labels or `workflow_dispatch`. It runs Codex on a GitHub-hosted runner or on a self-hosted VPS runner. GitHub Secrets provide credentials and environment configuration.

Pros:

- Native GitHub audit trail for workflow starts, logs, and failures.
- Natural integration with PR and CI checks.
- Easier visibility for queued/running/completed jobs.

Cons:

- Larger secrets and sandboxing risk.
- Harder environment parity with the VPS development checkout.
- Self-hosted runner on the VPS expands the attack surface.
- GitHub-hosted runner would need reproducible setup for Codex auth, Python, local configs, and repository policies.
- More complex to keep production paths, credentials, and deployment operations out of scope.

### Option C - Do Not Build / Docs-Only

Keep Level 1 manual workflow as the default and use this document as the design basis for a later implementation issue.

Pros:

- Lowest operational risk now.
- Preserves Operator review before every Codex prompt.
- Avoids automation around git, credentials, and PR creation before controls are accepted.

Cons:

- Does not reduce prompt-copying work.
- Does not provide automated queueing or run logs.

## Recommended Architecture If Built Later

If Level 2 is built, prefer a postponed VPS watcher/wrapper design.

Minimum architecture:

- Process only one active run at a time.
- Require both labels: `codex-ready` and `approved-by-operator`.
- Optionally enforce an Issue author whitelist.
- Refuse to start when the worktree is dirty.
- Create an issue-specific branch outside Codex.
- Run `codex exec` with `workspace-write` sandbox by default, not `danger-full-access`.
- Pass the approved Issue prompt to Codex through stdin or a wrapper-owned prompt file.
- Capture stdout, stderr, JSONL events, and final response.
- Enforce a timeout, initially 2 hours.
- Check diff scope after Codex completes.
- Run configured checks for the task.
- Commit, push, and open PR only when scope and checks pass.
- Comment the result on the Issue whether the run succeeds or fails.
- Never read or print `.env`.
- Never touch `/opt/duzman`.
- Never deploy, restart services, run migrations, or change credentials.

## State Machine

Suggested states:

- `queued`: Issue has candidate label but has not started.
- `approved`: Issue has all required gates and is eligible to run.
- `running`: wrapper has acquired the lock and launched or is about to launch Codex.
- `failed`: wrapper or Codex failed in a bounded way.
- `timed_out`: Codex or a verification command exceeded the timeout.
- `pr_created`: wrapper created a PR for the run.
- `cancelled`: Operator intentionally stopped or invalidated the run.
- `done`: PR merged or Operator marked the Issue as complete.

State should live in two places:

- GitHub labels/comments as the operator-visible source.
- `.agents/codex-dispatcher/runs/<issue-number>/run.json` for machine state.

Logs should be redacted before long-term retention. Retain enough to audit the prompt snapshot, runner behavior, exit code, checks, and PR link. A reasonable initial retention policy is 30 days for full logs and indefinite retention for compact run summaries.

## Concurrency And Idempotency

Start with one active run at a time.

Use a lock file containing PID, Issue number, branch name, and timestamp. If a lock appears stale, prefer manual Operator recovery first. A later version may add an explicit stale-lock policy, but automatic recovery should not run Codex twice for the same Issue without review.

Idempotency rules:

- If a PR already exists for the Issue, do not create another PR.
- If the branch already exists, either resume from recorded state or fail safely and ask Operator to resolve it.
- If a run already reached `pr_created`, future watcher cycles should only comment the existing PR link or do nothing.
- Reruns require an explicit label or comment command, not automatic infinite retries.
- Failed runs retain logs and state for inspection.

## Failure Modes

| Failure mode | Safe response |
| --- | --- |
| Codex exits non-zero | Stop, comment failure, retain logs, do not commit/push unless Operator manually decides. |
| Codex quota exhausted | Stop, comment quota/auth style failure, retain logs, no retry loop. |
| Auth failure | Stop, comment failure category, require Operator action. |
| Timeout or hang | Terminate child process, mark `timed_out`, comment failure, retain logs. |
| Empty diff | Comment no-op result, do not create PR unless Issue explicitly allowed docs/status-only output. |
| Tests fail | Comment failing command and summary, retain logs, do not push by default. |
| Push fails | Comment failure, retain local branch/logs, require Operator action. |
| PR creation fails | Comment failure if possible, retain branch/logs, require Operator action. |
| Invalid or unsafe Issue prompt | Refuse before running Codex, comment missing approval or unsafe scope. |
| Dirty working tree | Refuse before branch creation, comment dirty-worktree failure, require manual cleanup. |

No failure response should deploy, restart services, read secrets, change credentials, or access production DB.

## Security Model

Threat model: the Issue body becomes an executable prompt for a coding agent. Any GitHub user with Issue-writing permission could influence Codex unless additional controls exist.

Required controls:

- Require `approved-by-operator` after manual review.
- Optionally require author whitelist.
- Do not use `danger-full-access` by default.
- Keep `.env` and secret-like environment variables excluded.
- Forbid production paths, including `/opt/duzman`.
- Forbid deploy, systemd, migration, credential, firewall, package manager, and SSH operations.
- Redact token/key-like strings in logs.
- Keep an audit record for every run.
- Keep merge manual. PR creation is not merge authority.

## Audit Trail

Each run should record:

- Issue number, title, and URL.
- Prompt snapshot hash.
- Labels at run start.
- Branch name.
- Codex version.
- Start and end time.
- Exit code.
- Checks run and their results.
- Changed files.
- PR URL, if created.
- Failure reason, if any.
- Log paths.
- Wrapper version or commit SHA.

Recommended retention:

- Full raw/redacted logs: 30 days initially.
- Compact JSON run summaries: retain indefinitely or until Operator prunes them.
- GitHub Issue comments: permanent operator-visible audit trail.

## Build / Postpone Recommendation

Postpone full Level 2 automation for now.

Keep Level 1 manual workflow as the default. Create a separate implementation Issue only if Operator accepts the safety model in this document.

Suggested phased rollout:

1. Dry-run watcher only: detect eligible Issue, validate labels/author/worktree, and post a planned-action comment. Do not run Codex.
2. Codex-run MVP: run `codex exec`, capture logs, and report results, but keep commit/PR manual or behind a strict explicit flag.
3. Wrapper-managed git MVP: wrapper can commit/push/open PR only after scope checks and configured verification pass.

Production deploy must remain manual.

## Estimated Effort

- Research document: done in this PR.
- Dry-run watcher: 0.5-1 day.
- Safe MVP watcher with tests: 2-4 days.
- Hardened production-grade dispatcher: 1-2 weeks.

## Out Of Scope

- No implementation in this document.
- No GitHub Actions.
- No systemd units.
- No product DB changes.
- No alert or Telegram dispatcher changes.
- No production deploy.
- No automatic merge.
- No automatic production rollout.
- No trading, order, account, or private exchange logic.

## Future Implementation Issue Template

Title: Implement dry-run Codex Issue dispatcher

Goal:
Build a dry-run watcher that identifies Issues eligible for future Codex automation and comments the planned action without running Codex or changing git state.

Allowed files:

- `scripts/codex_issue_dispatcher.py`
- `tests/automation/test_codex_issue_dispatcher.py`
- `docs/research/codex_issue_dispatcher.md`
- `.agents/README.md` if local state documentation is needed

Safety constraints:

- Do not read or print `.env`.
- Do not touch `/opt/duzman`.
- Do not access production DB.
- Do not deploy or restart services.
- Do not run migrations.
- Do not modify credentials.
- Do not commit, push, or open PR in the dry-run implementation.
- Do not run Codex in the dry-run implementation.

Acceptance criteria:

- Detect Issues with `codex-ready` and `approved-by-operator`.
- Ignore Issues missing either required label.
- Refuse dirty worktree.
- Produce a deterministic planned-action comment body.
- Store dry-run state under `.agents/codex-dispatcher/`.
- Unit tests mock all `gh` calls and do not require network.
- Documentation explains how Operator reviews dry-run output.

Required tests:

- Eligible Issue produces planned action.
- Missing `approved-by-operator` is ignored.
- Missing `codex-ready` is ignored.
- Dirty worktree refuses run.
- Existing run state is idempotent.
- `gh` command failure is reported safely.
