"""Map the live hackathon Supabase columns onto the SPEC row models.

Part 2 SQL was never checked in. The deployed `incidents` table uses
`incident_id` / `reported_date` / `category` rather than `id` / `created_at` /
`hazard_category`. Reads normalize to `database.models`; FakeBackend tests keep
the SPEC column names.
"""

from __future__ import annotations

import json
from uuid import NAMESPACE_URL, UUID, uuid5

_LIVE_INCIDENT_MARKERS = frozenset({"reported_date", "incident_id", "risk_level", "category"})


def is_live_incident_row(row: dict) -> bool:
    keys = set(row)
    if keys & _LIVE_INCIDENT_MARKERS and "incident_ref" not in keys and "created_at" not in keys:
        return True
    return False


def coerce_uuid(value: object) -> UUID:
    text = str(value)
    try:
        return UUID(text)
    except (ValueError, TypeError, AttributeError):
        return uuid5(NAMESPACE_URL, f"sentinelloop:{text}")


def normalize_incident_row(row: dict) -> dict:
    if not is_live_incident_row(row):
        return row
    pk = row.get("incident_id")
    description = row.get("description") or row.get("title")
    return {
        "id": coerce_uuid(pk),
        "incident_ref": str(pk) if pk is not None else str(coerce_uuid("unknown")),
        "reporter_id": row.get("reporter_id") or "unknown",
        "source_channel": row.get("source_channel") or "whatsapp",
        "detected_language": row.get("reporter_language"),
        "hazard_category": row.get("category"),
        "hazard_description": description,
        "location": row.get("location"),
        "status": row.get("status") or "REPORTED",
        "current_risk_level": row.get("risk_level"),
        "duplicate_count": row.get("duplicate_count") or 0,
        "created_at": row.get("reported_date"),
        "resolved_at": row.get("resolved_date"),
        "closed_at": row.get("resolved_date") if str(row.get("status") or "").upper() == "CLOSED" else None,
        "original_message_text": description,
        "site_id": row.get("equipment_involved"),
        "is_anonymous": bool(row.get("is_anonymous") or False),
    }


def normalize_evidence_row(row: dict) -> dict:
    if "evidence_id" not in row and "uploaded_time" not in row:
        return row
    return {
        "id": coerce_uuid(row.get("evidence_id") or row.get("id")),
        "incident_id": coerce_uuid(row.get("incident_id")),
        "stage": row.get("evidence_stage") or row.get("stage"),
        "evidence_type": row.get("file_type") or row.get("evidence_type"),
        "source": row.get("source"),
        "storage_reference": row.get("file_url") or row.get("storage_reference"),
        "uploaded_by": row.get("uploaded_by"),
        "created_at": row.get("uploaded_time") or row.get("created_at"),
    }


def normalize_assignment_row(row: dict) -> dict:
    if "assignment_id" not in row and "assigned_person" not in row:
        return row
    return {
        "id": coerce_uuid(row.get("assignment_id") or row.get("id")),
        "incident_id": coerce_uuid(row.get("incident_id")),
        "team": row.get("department") or row.get("team"),
        "assigned_to": row.get("assigned_person") or row.get("assigned_to"),
        "assignment_status": row.get("assignment_status"),
        "assigned_at": row.get("due_time") or row.get("assigned_at"),
        "acknowledged_at": row.get("accepted_time") or row.get("acknowledged_at"),
        "completed_at": row.get("completion_time") or row.get("completed_at"),
        "created_at": row.get("accepted_time") or row.get("due_time") or row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def parse_update_envelope(message: object) -> dict | None:
    """Decode a demo/live JSON envelope stored in incident_updates.message."""
    payload: object = message
    if isinstance(message, str):
        text = message.strip()
        if not text.startswith("{"):
            return None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    if not any(key in payload for key in ("update_type", "demo_key", "metadata")):
        return None
    return payload


def normalize_update_row(row: dict) -> dict:
    if "update_id" not in row and "timestamp" not in row:
        return row
    message = row.get("message")
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else None
    update_type = row.get("update_type") or "timeline"
    previous = row.get("previous_status")
    new_status = row.get("status") or row.get("new_status")
    actor_type = row.get("actor_type")
    actor_ref = row.get("updated_by") or row.get("actor_reference")
    decoded = parse_update_envelope(message)
    if decoded is not None:
        update_type = decoded.get("update_type") or update_type
        previous = decoded.get("previous_status") or previous
        new_status = decoded.get("new_status") or new_status
        actor_type = decoded.get("actor_type") or actor_type
        actor_ref = decoded.get("actor_reference") or actor_ref
        inner_meta = decoded.get("metadata")
        if isinstance(inner_meta, dict):
            meta = {**(meta or {}), **inner_meta, "demo_key": decoded.get("demo_key")}
        elif decoded.get("demo_key"):
            meta = {**(meta or {}), "demo_key": decoded.get("demo_key")}
        message = decoded.get("message") or message
    return {
        "id": coerce_uuid(row.get("update_id") or row.get("id")),
        "incident_id": coerce_uuid(row.get("incident_id")),
        "update_type": update_type,
        "previous_status": previous,
        "new_status": new_status,
        "actor_type": actor_type,
        "actor_reference": actor_ref,
        "message": message,
        "metadata": meta,
        "created_at": row.get("timestamp") or row.get("created_at"),
    }


def normalize_risk_row(row: dict) -> dict:
    if "assessment_id" not in row and "final_score" not in row:
        return row
    return {
        "id": coerce_uuid(row.get("assessment_id") or row.get("id")),
        "incident_id": coerce_uuid(row.get("incident_id")),
        "severity": row.get("severity"),
        "severity_reason": row.get("explanation") or row.get("severity_reason"),
        "likelihood": row.get("likelihood"),
        "likelihood_reason": row.get("explanation") or row.get("likelihood_reason"),
        "risk_score": row.get("final_score") or row.get("risk_score"),
        "final_risk_level": row.get("final_risk_level"),
        "applied_overrides": row.get("applied_overrides"),
        "created_at": row.get("created_at"),
    }
