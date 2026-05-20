import importlib
import sys


def test_duzman_package_imports():
    """The package root should import without side effects."""
    module = importlib.import_module("duzman")

    assert module.__name__ == "duzman"


def test_settings_module_imports_without_repo_env(monkeypatch, tmp_path):
    """Settings should be importable without relying on repository .env files."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("duzman.settings", None)

    module = importlib.import_module("duzman.settings")

    assert module.settings.database_url == ""
    assert module.settings.ai_explanations_enabled is False
    assert module.settings.ai_explanation_model == "claude-sonnet-4-6"


def test_settings_rejects_opus_model(monkeypatch, tmp_path):
    """Day-8 AI explanations must not allow Opus-class models."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AI_EXPLANATION_MODEL", "claude-opus-4-1")
    sys.modules.pop("duzman.settings", None)

    try:
        importlib.import_module("duzman.settings")
    except ValueError as exc:
        assert "claude-opus models are forbidden" in str(exc)
    else:  # pragma: no cover - defensive assertion path.
        raise AssertionError("opus model validation did not fail")
