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
    rate_limit_requests_per_minute: int = 60  # simple global or per-user limit
    rate_limit_burst: int = 20
    pii_redaction_enabled: bool = True
    pii_redaction_patterns: str = "email,phone"  # simple comma list for future extensibility
    # Alert rule thresholds (configurables)
    alert_intensity_high_threshold: float = 0.8
    alert_avg_intensity_count: int = 5
    alert_avg_intensity_threshold: float = 0.7
    alert_emotion_streak_length: int = 3
    # Dynamic override flag
    dynamic_config_enabled: bool = True
    # External AI provider (Grok) config
    grok_api_key: str | None = os.getenv("GROK_API_KEY")
    grok_model: str = os.getenv("GROK_MODEL", "emotion-base-1")
    grok_timeout_seconds: float = float(os.getenv("GROK_TIMEOUT_SECONDS", "8"))
    grok_enabled: bool = os.getenv("GROK_ENABLED", "1") in {"1", "true", "True"}
    # Audio / transcripción
    enable_transcription: bool = os.getenv("ENABLE_TRANSCRIPTION", "0") in {"1", "true", "True"}
    max_audio_duration_sec: float = float(os.getenv("MAX_AUDIO_DURATION_SEC", "600"))  # límite duro para procesamiento

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if not settings.secret_key:
    logger.warning("SECRET_KEY vacío; generando uno temporal")
elif len(settings.secret_key) < 32:
    logger.warning("SECRET_KEY parece corto (<32 chars). Reemplázalo por uno más fuerte.")
