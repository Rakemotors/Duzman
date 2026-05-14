from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: str = "postgresql://duzman_app:PASSWORD@localhost:5432/duzman"
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id_alerts: str = ""
    telegram_chat_id_system: str = ""
    duzman_api_key: str = ""


settings = Settings()
