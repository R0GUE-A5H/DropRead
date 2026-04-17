
import os
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

_env = os.getenv("APP_ENV", "local")


class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str

    @property
    def DATABASE_URL(self) -> str:
        password = quote_plus(self.POSTGRES_PASSWORD)
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    serper_api_key: str
    serper_page_num: int = 20

    google_client_id: str
    google_client_secret: str

    app_name: str = "Newsletter AI Digest"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=f".env.{_env}",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


def get_settings():
    return Settings()
