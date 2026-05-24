"""Tests for duzman.settings (regression #66 + defense-in-depth)."""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def reload_settings_module():
    """Reload duzman.settings to re-evaluate module-level Settings()."""

    def _reload():
        import duzman.settings as mod
        return importlib.reload(mod)

    return _reload


def test_settings_ignores_unknown_env_keys(
    monkeypatch, tmp_path, reload_settings_module
):
    """#66 regression: extra .env keys must not raise ValidationError."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://fake:fake@localhost/fake\n"
        "BACKUP_GPG_PASSPHRASE=fake_passphrase_value\n"
        "TELEGRAM_CHAT_ID_BACKUP=fake_chat_id_value\n"
        "ANOTHER_UNKNOWN_KEY=whatever\n"
    )
    monkeypatch.chdir(tmp_path)
    mod = reload_settings_module()
    s = mod.Settings()
    assert s.database_url == "postgresql://fake:fake@localhost/fake"
    assert not hasattr(s, "backup_gpg_passphrase")
    assert not hasattr(s, "telegram_chat_id_backup")


def test_settings_repr_does_not_echo_extra_secret_values(
    monkeypatch, tmp_path, reload_settings_module
):
    """Defense-in-depth: extra-key values must not appear in repr/str."""
    unique_marker = "UNIQUE_TEST_MARKER_DO_NOT_LEAK_42"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://fake:fake@localhost/fake\n"
        f"BACKUP_GPG_PASSPHRASE={unique_marker}\n"
    )
    monkeypatch.chdir(tmp_path)
    mod = reload_settings_module()
    s = mod.Settings()
    assert unique_marker not in repr(s)
    assert unique_marker not in str(s)
