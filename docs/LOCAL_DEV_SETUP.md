# Local Development Setup

This repository uses a project-local Python virtual environment for development and test commands. Do not install Duzman Python dependencies globally.

## Create the virtual environment

From the repository root:

```bash
python3 -m venv .venv
```

The `.venv/` directory is ignored by git.

## Install dependencies

Upgrade pip inside the virtual environment:

```bash
.venv/bin/python -m pip install --upgrade pip
```

Install project dependencies into `.venv` only:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Do not use `sudo`, `apt`, global `pip install`, `pip install --user`, or shell profile changes for this setup.

## Run tests

Run pytest through the virtual environment:

```bash
.venv/bin/python -m pytest
```

Current status: pytest is runnable from `.venv`, but the repository currently has no test cases. Pytest exits with code 5 and reports `collected 0 items`.

Pytest also emits a `pytest-asyncio` deprecation warning because `asyncio_default_fixture_loop_scope` is not set. This is not a test failure, but it should be addressed when test configuration is expanded.

## Run Alembic checks

Show migration history:

```bash
.venv/bin/alembic history
```

Current status: this succeeds and shows the initial schema migration:

```text
<base> -> b009e25bfab4 (head), initial schema
```

Check the current database revision:

```bash
.venv/bin/alembic current
```

Current status: this command was attempted and fails before connecting to PostgreSQL because no database URL is configured for Alembic in the current shell. The observed failure is:

```text
KeyError: 'url'
```

Do not create or edit `.env` as part of routine test setup. A future task should define a safe local database configuration pattern for development and Alembic checks.

## Known current gaps

- There are no actual test files yet.
- Alembic `current` needs a safe local database configuration before it can report a live database revision.
- No application code was changed for this setup task.

