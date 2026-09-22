"""Request schemas for incident routes."""
from typing import Literal

from pydantic import BaseModel, Field

IncidentStatus = Literal["open", "investigating", "identified", "monitoring", "resolved"]
IncidentSeverity = Literal["low", "medium", "high", "critical"]


class IncidentCreate(BaseModel):
    api_id: str = Field(min_length=24, max_length=24)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    severity: IncidentSeverity = "medium"


class IncidentUpdate(BaseModel):
    status: IncidentStatus | None = None
    severity: IncidentSeverity | None = None
    root_cause: str | None = Field(default=None, max_length=5000)
    resolution_notes: str | None = Field(default=None, max_length=5000)


class IncidentResolve(BaseModel):
    resolution_notes: str = Field(default="", max_length=5000)
