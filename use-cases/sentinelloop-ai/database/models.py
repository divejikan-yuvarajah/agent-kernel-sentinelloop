"""Pydantic row models for the five SentinelLoop Supabase tables.

Part 2 of the team build guide (SQL already applied in Supabase) was not
present as a file in this repository. Column names follow SPEC.md plus the
explicit Part 2 deltas from the persistence prompt: incidents.duplicate_count
and incident_evidence.stage. Extra database columns are ignored on parse
(extra=ignore) so undocumented SQL fields do not crash reads.

Pydantic v2 (repository: pydantic>=2.11, installed 2.x).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from database.schemas import parse_ternary


class _RowModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Incident(_RowModel):
    """Row from `incidents`."""

    id: UUID
    incident_ref: str
    reporter_id: str
    session_id: str | None = None
    source_channel: str
    detected_language: str | None = None
    hazard_category: str | None = None
    hazard_description: str | None = None
    location: str | None = None
    injury_occurred: bool | None = None
    hazard_currently_active: bool | None = None
    people_exposed: int | None = None
    status: str
    current_risk_level: str | None = None
    duplicate_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    original_message_id: str | None = None
    original_message_text: str | None = None
    site_id: str | None = None
    duplicate_of: UUID | None = None
    reopen_count: int | None = None
    is_anonymous: bool = False

    @field_validator("injury_occurred", "hazard_currently_active", mode="before")
    @classmethod
    def _ternary(cls, value: object) -> bool | None:
        return parse_ternary(value)


class IncidentEvidence(_RowModel):
    """Row from `incident_evidence`."""

    id: UUID
    incident_id: UUID
    stage: str | None = None
    evidence_type: str | None = None
    source: str | None = None
    storage_reference: str | None = None
    external_message_id: str | None = None
    caption_or_description: str | None = None
    uploaded_by: str | None = None
    created_at: datetime | None = None


class RiskAssessment(_RowModel):
    """Row from `risk_assessments`."""

    id: UUID
    incident_id: UUID
    severity: int | None = None
    severity_reason: str | None = None
    likelihood: int | None = None
    likelihood_reason: str | None = None
    risk_score: int | None = None
    base_risk_level: str | None = None
    final_risk_level: str | None = None
    applied_overrides: list[str] | None = None
    assessment_version: int | None = None
    created_at: datetime | None = None


class Assignment(_RowModel):
    """Row from `assignments`."""

    id: UUID
    incident_id: UUID
    team: str | None = None
    slack_channel_id: str | None = None
    assigned_to: str | None = None
    assignment_status: str | None = None
    assigned_at: datetime | None = None
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IncidentUpdate(_RowModel):
    """Row from `incident_updates` (durable timeline)."""

    id: UUID
    incident_id: UUID
    update_type: str
    previous_status: str | None = None
    new_status: str | None = None
    actor_type: str | None = None
    actor_reference: str | None = None
    message: str | None = None
    metadata: dict[str, Any] | None = Field(default=None)
    created_at: datetime | None = None
