"""Read-only local PostgreSQL readiness check for operator-controlled runtimes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import os
import sys
from typing import TextIO

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from duzman.logging_config import safe_error_message


REQUIRED_STAGE_A_TABLES: frozenset[str] = frozenset(
    {
        "price_snapshots",
        "source_health_checks",
    }
)
SUCCESS_MESSAGE = "LOCAL_DATABASE_CHECK_OK"

EngineFactory = Callable[[str], Engine]
DatabaseUrlProvider = Callable[[], str | None]
DatabaseVerifier = Callable[[str], "LocalDatabaseVerificationResult"]


@dataclass(frozen=True)
class LocalDatabaseVerificationResult:
    """Non-secret result from the local database readiness check."""

    confirmed_tables: tuple[str, ...]


class LocalDatabaseVerificationError(RuntimeError):
    """Controlled failure for local database verification without secret details."""


def verify_local_database(
    database_url: str,
    engine_factory: EngineFactory = create_engine,
) -> LocalDatabaseVerificationResult:
    """Verify read-only connectivity and required Stage A tables."""
    if not database_url:
        raise LocalDatabaseVerificationError(
            "DATABASE_URL is required for this command. Provide it inline for one "
            "operator-controlled invocation."
        )

    try:
        engine = engine_factory(database_url)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
                existing_tables = set(inspect(connection).get_table_names())
        finally:
            engine.dispose()
    except LocalDatabaseVerificationError:
        raise
    except Exception as exc:
        raise LocalDatabaseVerificationError(
            "local database connectivity check failed"
        ) from exc

    missing_tables = sorted(REQUIRED_STAGE_A_TABLES - existing_tables)
    if missing_tables:
        missing = ", ".join(missing_tables)
        raise LocalDatabaseVerificationError(
            f"local database schema is missing required table(s): {missing}"
        )

    confirmed_tables = tuple(sorted(REQUIRED_STAGE_A_TABLES))
    return LocalDatabaseVerificationResult(confirmed_tables=confirmed_tables)


def main(
    argv: Sequence[str] | None = None,
    database_url_provider: DatabaseUrlProvider | None = None,
    verifier: DatabaseVerifier = verify_local_database,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the local database readiness check and return a process exit code."""
    del argv
    resolved_provider = database_url_provider or _read_database_url_from_environment
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr

    try:
        result = verifier(resolved_provider() or "")
    except LocalDatabaseVerificationError as exc:
        print(safe_error_message(exc), file=error_stream)
        return 1
    except Exception as exc:
        error_type = type(exc).__name__
        print(f"local database verification failed: {error_type}", file=error_stream)
        return 1

    confirmed = ",".join(result.confirmed_tables)
    print(f"{SUCCESS_MESSAGE} confirmed_tables={confirmed}", file=output_stream)
    return 0


def _read_database_url_from_environment() -> str | None:
    return os.environ.get("DATABASE_URL")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
