from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from process environment or local env files."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: str = ""
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id_alerts: str = ""
    telegram_chat_id_system: str = ""
    duzman_api_key: str = ""
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


settings = Settings()
