"""Request schemas for settings and webhook routes."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

WebhookEvent = Literal["incident.created", "incident.resolved", "api.down", "api.recovered"]
WEBHOOK_EVENTS = ("incident.created", "incident.resolved", "api.down", "api.recovered")


class NotificationsUpdate(BaseModel):
    email_enabled: bool | None = None
    webhook_enabled: bool | None = None


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = None  # read-only; accepted but ignored


class SettingsUpdate(BaseModel):
    default_timeout: int | None = Field(default=None, ge=1, le=120)
    default_interval: int | None = None
    failure_threshold: int | None = Field(default=None, ge=1, le=20)
    recovery_threshold: int | None = Field(default=None, ge=1, le=20)
    degraded_latency_ms: int | None = Field(default=None, ge=1)
    results_retention_days: int | None = Field(default=None, ge=1, le=365)
    notifications: NotificationsUpdate | None = None
    profile: ProfileUpdate | None = None


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    events: list[str] = Field(min_length=1)
    active: bool = True

    @field_validator("events")
    @classmethod
    def validate_events(cls, v: list[str]) -> list[str]:
        bad = [e for e in v if e not in WEBHOOK_EVENTS]
        if bad:
            raise ValueError(f"invalid events: {bad}; allowed: {list(WEBHOOK_EVENTS)}")
        return v
