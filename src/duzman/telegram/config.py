# src/duzman/telegram/config.py
# Telegram settings layer. Reads only environment-backed configuration and never
# persists bot tokens or chat identifiers.
"""Configuration for Telegram long-polling delivery."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramSettings(BaseSettings):
    """Runtime settings for the Telegram integration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")
    alert_poll_interval_seconds: int = Field(
        default=30,
        alias="TELEGRAM_ALERT_POLL_INTERVAL_SECONDS",
        ge=1,
    )
    startup_lookback_hours: int = Field(
        default=24,
        alias="TELEGRAM_STARTUP_LOOKBACK_HOURS",
        ge=1,
    )
    enabled: bool = Field(default=True, alias="TELEGRAM_ENABLED")

    @property
    def configured(self) -> bool:
        """Return whether token and chat id are available."""
        return bool(self.bot_token and self.chat_id)

    @property
    def safe_disabled_reason(self) -> str | None:
        """Return a log-safe reason when Telegram delivery is disabled."""
        if not self.enabled:
            return "telegram_disabled_by_config"
        if not self.bot_token:
            return "telegram_bot_token_missing"
        if not self.chat_id:
            return "telegram_chat_id_missing"
        return None


def load_telegram_settings() -> TelegramSettings:
    """Load Telegram settings from process environment and local env file."""
    return TelegramSettings()
