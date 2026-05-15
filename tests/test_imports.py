import importlib
import sys


def test_duzman_package_imports():
    """The package root should import without side effects."""
    module = importlib.import_module("duzman")

    assert module.__name__ == "duzman"


def test_settings_module_imports_without_repo_env(monkeypatch, tmp_path):
    """Settings should be importable without relying on repository .env files."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://duzman_app:PASSWORD@localhost:5432/duzman",
    )
    sys.modules.pop("duzman.settings", None)

    module = importlib.import_module("duzman.settings")

    assert module.settings.database_url.startswith("postgresql://")

