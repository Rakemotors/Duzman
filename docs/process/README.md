# docs/process/

Project-wide process documentation: review discipline, runbook
discipline, lessons learned, and archived review logs.

## Scope

This directory contains rules and history that apply to the whole
project regardless of which agent or operator is acting. It is the
canonical location for:

- Review protocols (how PRs and runbooks are reviewed).
- Runbook discipline (what is and is not allowed during operational
  verification on production).
- Process lessons learned, with references to the SHAs or PRs that
  surfaced them.
- Archived review logs from external reviewers.

## Layout

    docs/process/
        README.md                 -- this file: index and archival rules
        REVIEW_PROTOCOL.md        -- review and runbook discipline
        reviews/                  -- archived review logs

Future additions (lessons/, postmortems/, etc.) should be added here
and listed in this README.

## Archival rules

- Format: Markdown only. Binary documents (e.g. .docx, .pdf) are
  avoided unless explicitly justified. Markdown is diffable,
  searchable, and reviewable in normal GitHub PR flow.
- Naming for dated artifacts: `YYYY-MM-DD_<short-topic>.md`.
  Example: `2026-05-23_day9d_chatgpt_interim_review.md`.
- Naming for protocol documents: `UPPER_SNAKE_CASE.md` (e.g.
  `REVIEW_PROTOCOL.md`).
- No secrets in any file under docs/process/. No API keys, tokens,
  passphrases, refresh tokens, chat ids, or full URLs containing
  credentials.

## Related but separate locations

- `.claude/skills/duzman-conventions/SKILL.md` contains
  Claude-specific operating conventions, while `docs/process/`
  contains project-wide process rules for all agents and operators.
- `docs/ARCHITECTURE.md` describes the system structure and module
  relationships, not process.
- `docs/TZ.md` is the source of truth for product and technical
  specification, not process.
- `AGENTS.md` (if present at repo root) describes agent roles and
  responsibilities; it does not duplicate review or runbook rules
  defined here.
