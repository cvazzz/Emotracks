import os
from functools import lru_cache
import secrets
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    app_name: str = "EmoTrack Kids"
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://postgres:postgres@db:5432/emotrack"
    )
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if not settings.secret_key:
    logger.warning("SECRET_KEY vacío; generando uno temporal")
elif len(settings.secret_key) < 32:
    logger.warning("SECRET_KEY parece corto (<32 chars). Reemplázalo por uno más fuerte.")
