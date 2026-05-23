# 2026-05-23 — Day 9D ChatGPT Interim Review Log

## Context

During Day 9D VPS verification for PR #60, the local encrypted
backup service initially failed during runtime smoke testing. The
primary reviewer (Claude) was outside its rate-limit window for
part of this period. An independent interim review was performed
by ChatGPT to keep verification moving and to provide a second
opinion on the proposed fix.

This file archives that interim review for institutional memory.

## Observed failures

1. The first backup run failed at `pg_dump` because
   `/opt/duzman/.env` had a stale `DATABASE_URL`.
2. After fixing `DATABASE_URL`, the backup reached
   `encrypt_archive` but failed because `gpg` attempted to create
   `/opt/duzman/.gnupg` under a systemd sandbox where
   `/opt/duzman` is read-only.
3. A runtime hotfix was applied to set `GNUPGHOME` inside the
   temporary backup working directory.
4. The first hotfix attempt used the wrong variable name,
   `WORK_DIR`; the actual script variable was `WORKDIR`.
5. After correcting the variable, backup completed successfully
   and delivered the encrypted `.tar.gz.gpg` file to Telegram.

## Technical conclusion

The final technical fix was correct:

- `GNUPGHOME="${WORKDIR}/gnupg"` keeps gpg writable state inside
  the script's temporary work directory.
- The temporary work directory is removed by the existing cleanup
  trap.
- The systemd sandbox remained intact.
- `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true`,
  and `ReadWritePaths=/opt/duzman/backups` were not weakened.

## Process issue

The fix was technically correct, but it was pushed directly to the
active PR branch during the VPS runbook. This created a process
gap because the new commit had not been part of the previously
reviewed SHA.

Reference case:

- Previous reviewed SHA: 39d3076
- Follow-up hotfix SHA: 09d7057
- Final merged main HEAD after rebase: 3a23d60

## Cross-review value

The Telegram-token-in-argv issue had been independently identified
by both Claude and ChatGPT in earlier rounds of Day 9D review.
This provides evidence that the review process is robust to
single-reviewer error: two independent models reached the same
security finding without prompting each other.

This is also a reference for future situations where the primary
reviewer is unavailable: an independent second model can be used
for interim review, and the resulting log should be archived here.

## Outcome

Day 9D was completed successfully and PR #60 was merged after
follow-up review. The process lesson is preserved in
`docs/process/REVIEW_PROTOCOL.md`. The new protocol must be in
place before Day 9E begins, because Day 9E introduces another
infra-sensitive runbook involving rclone, OneDrive OAuth, secrets,
and systemd timers.
