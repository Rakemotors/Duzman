import pytest


def test_verify_local_database_main_fails_safely_without_database_url(
    monkeypatch,
    capsys,
):
    """Missing DATABASE_URL should produce a controlled non-secret failure."""
    from duzman.runtime import verify_local_database

    monkeypatch.delenv("DATABASE_URL", raising=False)

    exit_code = verify_local_database.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "DATABASE_URL is required" in captured.err
    assert "postgresql://" not in captured.err
    assert captured.out == ""


def test_verify_local_database_main_reports_success_with_injected_verifier(capsys):
    """The success path should be testable without a live PostgreSQL server."""
    from duzman.runtime import verify_local_database

    def fake_verifier(database_url: str):
        assert database_url == "postgresql+psycopg://placeholder"
        return verify_local_database.LocalDatabaseVerificationResult(
            confirmed_tables=("price_snapshots", "source_health_checks")
        )

    exit_code = verify_local_database.main(
        database_url_provider=lambda: "postgresql+psycopg://placeholder",
        verifier=fake_verifier,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LOCAL_DATABASE_CHECK_OK" in captured.out
    assert "price_snapshots,source_health_checks" in captured.out
    assert captured.err == ""


def test_verify_local_database_detects_missing_required_tables(monkeypatch):
    """Schema readiness checks should fail clearly without writing rows."""
    from duzman.runtime import verify_local_database

    fake_engine = _FakeEngine()

    monkeypatch.setattr(
        verify_local_database,
        "inspect",
        lambda connection: _FakeInspector(table_names=("price_snapshots",)),
    )

    with pytest.raises(verify_local_database.LocalDatabaseVerificationError) as exc:
        verify_local_database.verify_local_database(
            "postgresql+psycopg://placeholder",
            engine_factory=lambda database_url: fake_engine,
        )

    assert "source_health_checks" in str(exc.value)
    assert fake_engine.disposed is True
    assert fake_engine.connection.executed_statements == ["SELECT 1"]


def test_verify_local_database_redacts_connection_failures():
    """Low-level DB failures should not expose URL, user, host, or password."""
    from duzman.runtime import verify_local_database

    def fail_engine(database_url: str):
        raise RuntimeError(
            "could not connect DATABASE_URL=postgresql://fake_user:"
            "fake_password@fake-host:5432/fake_db password=fake_password"
        )

    with pytest.raises(verify_local_database.LocalDatabaseVerificationError) as exc:
        verify_local_database.verify_local_database(
            "postgresql://fake_user:fake_password@fake-host:5432/fake_db",
            engine_factory=fail_engine,
        )

    message = str(exc.value)
    assert message == "local database connectivity check failed"
    assert "fake_password" not in message
    assert "fake-host" not in message
    assert "fake_db" not in message


def test_verify_local_database_main_bounds_unexpected_failures(capsys):
    """Unexpected verifier failures should not print raw secret-looking values."""
    from duzman.runtime import verify_local_database

    def fail_with_secret_like_message(database_url: str):
        raise RuntimeError(
            "DATABASE_URL=postgresql://fake_user:fake_password@fake-host/fake_db"
        )

    exit_code = verify_local_database.main(
        database_url_provider=lambda: "postgresql://fake_user:fake_password@fake-host/fake_db",
        verifier=fail_with_secret_like_message,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "local database verification failed: RuntimeError" in captured.err
    assert "fake_password" not in captured.err
    assert "fake-host" not in captured.err
    assert "fake_db" not in captured.err


def test_verify_local_database_does_not_start_scheduler(monkeypatch, capsys):
    """The local database check should not start APScheduler or collection jobs."""
    import duzman.runtime.market_data_scheduler as scheduler_runtime
    from duzman.runtime import verify_local_database

    def fail_if_scheduler_starts(*args, **kwargs):
        raise AssertionError("database verification must not start APScheduler")

    monkeypatch.setattr(
        scheduler_runtime,
        "run_market_data_scheduler_forever",
        fail_if_scheduler_starts,
    )

    exit_code = verify_local_database.main(
        database_url_provider=lambda: "postgresql+psycopg://placeholder",
        verifier=lambda database_url: verify_local_database.LocalDatabaseVerificationResult(
            confirmed_tables=("price_snapshots", "source_health_checks")
        ),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "LOCAL_DATABASE_CHECK_OK" in captured.out


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()
        self.disposed = False

    def connect(self):
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


class _FakeConnection:
    def __init__(self) -> None:
        self.executed_statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, statement):
        self.executed_statements.append(str(statement))
        return _FakeScalarResult()


class _FakeScalarResult:
    def scalar_one(self) -> int:
        return 1


class _FakeInspector:
    def __init__(self, table_names: tuple[str, ...]) -> None:
        self._table_names = table_names

    def get_table_names(self) -> list[str]:
        return list(self._table_names)
