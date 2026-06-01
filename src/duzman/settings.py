from typing import Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from process environment or local env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str | None = None
    telegram_timeout_ms: int = 5000
    telegram_enabled: bool = False
    telegram_chat_id_alerts: str = ""
    telegram_chat_id_system: str = ""
    duzman_api_key: SecretStr = SecretStr("")
    coinglass_api_key: SecretStr | None = None
    ai_explanations_enabled: bool = False
    ai_explanation_model: str = "claude-sonnet-4-6"
    ai_explanation_fallback_model: str = "claude-sonnet-4-5-20250929"
    ai_explanation_max_per_hour: int = 10
    ai_explanation_max_per_day: int = 50
    ai_explanation_timeout_seconds: int = 20
    ai_explanation_max_input_chars: int = 6000
    ai_explanation_max_output_tokens: int = 500
    ai_explanation_cache_window_minutes: int = 15
    ai_explanation_worker_poll_seconds: int = 30
    ai_explanation_running_stale_minutes: int = 10
    ai_explanation_retry_max: int = 1

    @field_validator("ai_explanation_model", "ai_explanation_fallback_model")
    @classmethod
    def _reject_opus_models(cls, value: str) -> str:
        """Reject Opus-class models for the day-8 MVP cost envelope."""
        if value.startswith("claude-opus"):
            raise ValueError("claude-opus models are forbidden for day 8 AI explanations")
        return value

    @field_validator("telegram_timeout_ms")
    @classmethod
    def _validate_telegram_timeout_ms(cls, value: int) -> int:
        """Validate Telegram HTTP timeout bounds."""
        if value < 1000 or value > 30000:
            raise ValueError("telegram_timeout_ms must be between 1000 and 30000")
        return value

    @model_validator(mode="after")
    def _validate_telegram_enabled_settings(self) -> Self:
        """Require Telegram credentials only when Telegram dispatch is enabled."""
        token = (
            self.telegram_bot_token.get_secret_value()
            if self.telegram_bot_token is not None
            else ""
        )
        if self.telegram_enabled and not token:
            raise ValueError(
                "telegram_bot_token is required when telegram_enabled is true"
            )
        if self.telegram_enabled and not self.telegram_chat_id:
            raise ValueError("telegram_chat_id is required when telegram_enabled is true")
        return self


settings = Settings()
