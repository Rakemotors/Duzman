# REVIEW_PROTOCOL

Project-wide rules for reviewing pull requests, conducting
production verification runbooks, and preserving important specs in
durable project documentation.

## Gate policy for operational PRs

For PRs that touch deploy scripts, systemd units, runtime entrypoints,
backups, secrets handling, or anything production-adjacent, reviewer
APPROVE does not mean OK TO MERGE.

Required flow:

1. Reviewer posts a review comment marked "DO NOT MERGE YET" with an
   explicit list of VPS verification steps the operator must perform.
2. Operator executes the steps on the VPS and posts the results.
3. Only after operator posts an explicit "OK TO MERGE" comment may
   the PR be merged.

Docs-only and test-only PRs may follow normal APPROVE → merge.

## Spec durability rule

Important implementation specs, review protocols, operational
runbooks, and process decisions must live in durable project
documentation, not only in chat.

Durable locations:

- GitHub Issue body.
- Pull Request description.
- `docs/specs/` for approved standalone specs.
- `docs/process/` for project-wide process rules and archived review
  logs.

Chat-only specs are not durable documentation. If a chat message
contains requirements that future reviewers, agents, or operators
must rely on, those requirements must be copied into one of the
durable locations above before implementation or merge.

## No hotfix directly on PR branch during VPS runbook

During execution of a VPS runbook attached to an open PR, if the
smoke verification fails:

Required flow:

1. Stop the runbook immediately.
2. Record the failure and non-secret logs in the PR comment thread.
3. Open a follow-up task or use the existing issue. Hand the task to
   Codex with a written spec.
4. Codex implements the fix and pushes a new commit to the PR branch.
5. Reviewer performs a follow-up review on the new SHA.
6. Operator resumes VPS verification only after review approval.

Direct hotfix commits on the PR branch from the operator's machine
or from the VPS, bypassing Codex and reviewer, are not allowed even
when the fix is small or obvious. The reason is audit trail: every
SHA that lands on main must have been reviewed on a known prior SHA.

## Reference case: Day 9D, SHA 09d7057

During Day 9D VPS verification for PR #60 (local encrypted daily
backup), gpg failed under the systemd sandbox because it attempted
to create `/opt/duzman/.gnupg` in a read-only path. A runtime fix
was applied that set `GNUPGHOME` inside the script's temporary work
directory.

- Previously reviewed SHA: 39d3076
- Follow-up hotfix SHA: 09d7057
- Final merged main HEAD after merge: 3a23d60

The technical fix was correct and was post-verified by the
reviewer. However, the commit was pushed directly to the PR branch
during the runbook rather than going through the
Codex → push → re-review cycle. This is the anti-pattern that this
protocol exists to prevent.

## Secrets discipline during review and runbooks

- No secrets in diffs, commit messages, runbook outputs, or
  Telegram notifications.
- Reviewer must reject any PR or runbook output that leaks secrets,
  regardless of merge urgency.
- Operator must redact secrets before pasting any VPS output into
  the PR thread.
