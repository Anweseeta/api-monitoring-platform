"""Application configuration loaded from environment variables.

Field names are the canonical (lowercase) names; several fields also accept
the deploy-style uppercase aliases used in `.env.example` and `render.yaml`
(e.g. ACCESS_TOKEN_EXPIRE_MINUTES). Unknown env vars are ignored.
"""
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Runtime environment: "development" | "production".
    # Production enables fail-fast guards (e.g. refusing the default JWT secret).
    environment: str = "development"

    # Database
    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "apimonitor"

    # Auth
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = Field(
        default=60,
        validation_alias=AliasChoices("jwt_expires_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES"),
    )

    # Frontend / CORS
    frontend_url: str = "http://localhost:5173"

    # Monitoring engine
    backend_public_url: str = "http://localhost:8000"
    monitor_allow_loopback: bool = True
    incident_escalation_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("incident_escalation_minutes", "INCIDENT_ESCALATION_MINUTES"),
    )

    # Monitoring defaults (per-user settings merge over these)
    default_interval: int = Field(
        default=300,
        validation_alias=AliasChoices("default_interval", "MONITOR_DEFAULT_INTERVAL"),
    )
    default_timeout: int = Field(
        default=10,
        validation_alias=AliasChoices("default_timeout", "MONITOR_DEFAULT_TIMEOUT"),
    )
    failure_threshold: int = Field(
        default=3,
        validation_alias=AliasChoices("failure_threshold", "FAILURE_THRESHOLD"),
    )
    recovery_threshold: int = Field(
        default=2,
        validation_alias=AliasChoices("recovery_threshold", "RECOVERY_THRESHOLD"),
    )
    degraded_latency_ms: int = Field(
        default=1000,
        validation_alias=AliasChoices("degraded_latency_ms", "DEGRADED_LATENCY_MS"),
    )
    results_retention_days: int = Field(
        default=30,
        validation_alias=AliasChoices("results_retention_days", "RESULTS_RETENTION_DAYS"),
    )

    # Notifications (SMTP optional)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = Field(
        default="",
        validation_alias=AliasChoices("smtp_user", "SMTP_USERNAME"),
    )
    smtp_password: str = ""
    smtp_from: str = ""

    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """For tests that mutate env vars between cases."""
    get_settings.cache_clear()
