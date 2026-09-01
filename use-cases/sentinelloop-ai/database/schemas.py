"""Create, update, filter, and evidence-file payloads for the repository.

Callers must not set generated primary keys or database timestamps.
SPEC.md remains the product contract; these schemas only cover columns the
persistence layer is allowed to write.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 50

# Application-level stage values from the persistence prompt. If Part 2 SQL
# uses different strings, widen this set rather than inventing extra columns.
EVIDENCE_STAGES = frozenset({"report", "remediation", "verification"})


def parse_ternary(value: Any) -> Any:
    """Map SQL boolean / text / unknown onto bool | None (None = unknown)."""
    if value is None or value == "unknown":
        return None
    if value in (True, "true", "t", "yes", "True"):
        return True
    if value in (False, "false", "f", "no", "False"):
        return False
    return value


class _InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IncidentCreate(_InputModel):
    """Insert payload for `incidents`. duplicate_count is a database default."""

    incident_ref: str
    reporter_id: str
    source_channel: str = "telegram"
    session_id: str | None = None
    detected_language: str | None = None
    hazard_category: str | None = None
    hazard_description: str | None = None
    location: str | None = None
    injury_occurred: bool | None = None
    hazard_currently_active: bool | None = None
    people_exposed: int | None = None
    status: str = "REPORTED"
    current_risk_level: str | None = None
    original_message_id: str | None = None
    original_message_text: str | None = None
    site_id: str | None = None
    telegram_chat_id: str | None = None
    telegram_user_id: str | None = None
    telegram_message_id: str | None = None
    input_method: str | None = None
    created_by: str | None = None
    source_metadata: dict[str, Any] | None = None
    pipeline_version: str | None = None
    is_sandbox: bool = False

    @field_validator("injury_occurred", "hazard_currently_active", mode="before")
    @classmethod
    def _ternary(cls, value: object) -> bool | None:
        return parse_ternary(value)


class IncidentStatusUpdate(_InputModel):
    status: str


class IncidentFilters(_InputModel):
    """Allowlisted list filters. Unknown fields are rejected (extra=forbid)."""

    status: str | None = None
    current_risk_level: str | None = None
    hazard_category: str | None = None
    detected_language: str | None = None
    reporter_id: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = DEFAULT_LIST_LIMIT
    offset: int = 0

    @field_validator("limit")
    @classmethod
    def cap_limit(cls, value: int) -> int:
        if value < 1:
            return 1
        return min(value, MAX_LIST_LIMIT)

    @field_validator("offset")
    @classmethod
    def min_offset(cls, value: int) -> int:
        return max(value, 0)


class AssignmentCreate(_InputModel):
    incident_id: UUID
    team: str | None = None
    slack_channel_id: str | None = None
    assigned_to: str | None = None
    assignment_status: str = "assigned"


class IncidentUpdateCreate(_InputModel):
    incident_id: UUID
    update_type: str
    previous_status: str | None = None
    new_status: str | None = None
    actor_type: str | None = None
    actor_reference: str | None = None
    message: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class EvidenceFile:
    """Transport-neutral file payload (Telegram media or dashboard upload)."""

    content: bytes
    filename: str | None = None
    content_type: str | None = None


class EvidenceCreate(_InputModel):
    """Optional metadata persisted with an evidence row (no file bytes)."""

    evidence_type: str | None = None
    source: str | None = None
    caption_or_description: str | None = None
    uploaded_by: str | None = None
    external_message_id: str | None = None
