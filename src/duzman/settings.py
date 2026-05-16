from pydantic import SecretStr
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


settings = Settings()
