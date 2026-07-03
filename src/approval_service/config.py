"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "APP_"}

    database_url: str = "sqlite+aiosqlite:///./approval.db"
    log_level: str = "INFO"


settings = Settings()
