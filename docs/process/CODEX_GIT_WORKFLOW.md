# Codex git workflow

## Limitation

Inside the Codex CLI sandbox, `~/duzman` is mounted read-write but
`~/duzman/.git` is mounted read-only. Codex can edit project files and run
local verification, but cannot create branches, stage files, commit, or push
from inside the sandbox.

## Sanctioned workflow

1. Codex edits files in `~/duzman` and runs the minimum local verification
   required by the task.
2. Operator, in a plain bash shell outside Codex sandbox, performs:
   `git checkout -b <branch>`, `git add <explicit files>`, `git commit`,
   `git push`, `gh pr create`.
3. Operator never uses `git add .` and never stages files Codex did not
   explicitly list in its task summary.
4. Review and merge proceed per `docs/process/REVIEW_PROTOCOL.md`.

## Audit reference

Investigation: `docs/process/codex_git_investigation.md`

Root cause as documented there: read-only bind-mount of `.git` at sandbox
level. Not a deny-rule, not a chmod issue, not a credentials issue.

## When to revisit

Reopen investigation if any of:

- Codex CLI version changes.
- `sandbox_mode` or `approval_policy` changes.
- Manual git workflow becomes a sustained source of operator error.
