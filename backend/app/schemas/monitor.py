"""Request schemas for monitor routes."""
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]
ALLOWED_INTERVALS = (60, 300, 600, 900, 1800, 3600)
BODY_METHODS = ("POST", "PUT", "PATCH")


class MonitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    method: HttpMethod = "GET"
    description: str = Field(default="", max_length=2000)
    interval: int = 300
    timeout: int = Field(default=10, ge=1, le=120)
    expected_status: int = Field(default=200, ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    active: bool = True

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v not in ALLOWED_INTERVALS:
            raise ValueError(f"interval must be one of {list(ALLOWED_INTERVALS)}")
        return v

    @model_validator(mode="after")
    def validate_body_method(self) -> "MonitorCreate":
        if self.body is not None and self.method not in BODY_METHODS:
            raise ValueError(f"body is only allowed for {', '.join(BODY_METHODS)} requests")
        return self


class MonitorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2048)
    method: HttpMethod | None = None
    description: str | None = Field(default=None, max_length=2000)
    interval: int | None = None
    timeout: int | None = Field(default=None, ge=1, le=120)
    expected_status: int | None = Field(default=None, ge=100, le=599)
    headers: dict[str, str] | None = None
    body: Any = None
    active: bool | None = None

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: int | None) -> int | None:
        if v is not None and v not in ALLOWED_INTERVALS:
            raise ValueError(f"interval must be one of {list(ALLOWED_INTERVALS)}")
        return v
