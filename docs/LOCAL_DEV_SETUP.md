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

Current status: pytest is runnable from `.venv` and the initial offline test suite passes.

## Database configuration

Duzman does not provide a default database password or fallback connection string in code. Runtime commands that open database sessions require `DATABASE_URL` to be configured by the Operator.

The offline test suite does not require `DATABASE_URL`, `.env`, or a live PostgreSQL connection.

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

- Alembic `current` needs a safe local database configuration before it can report a live database revision.
- The current tests validate imports, SQLAlchemy metadata, Alembic file presence, and ORM/migration schema consistency without connecting to PostgreSQL.
