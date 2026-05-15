from pathlib import Path


def test_alembic_files_exist():
    """Alembic should have a repository-local environment and migration file."""
    alembic_dir = Path("src/duzman/db/alembic")
    versions_dir = alembic_dir / "versions"

    assert (alembic_dir / "env.py").is_file()
    assert (alembic_dir / "script.py.mako").is_file()
    assert versions_dir.is_dir()
    assert any(versions_dir.glob("*.py"))

