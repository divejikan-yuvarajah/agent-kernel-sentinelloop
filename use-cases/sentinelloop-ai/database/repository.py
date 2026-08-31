"""CRUD for SentinelLoop durable tables.

Does not calculate risk, route Slack, or touch Agent Kernel sessions.
Supabase table access stays in this module.

Status + timeline writes are sequential, not a database transaction. If
add_update fails after update_incident_status, the caller sees the error;
this client has no RPC/transaction wrapper in the existing schema.
"""

from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from storage3.types import FileOptions
from supabase import Client

from database.client import evidence_bucket_name, get_supabase_client
from database.exceptions import (
    EvidenceUploadError,
    PartialPersistenceError,
    PersistenceError,
    RecordNotFoundError,
)
from database.models import Assignment, Incident, IncidentEvidence, IncidentUpdate
from database.schemas import (
    EVIDENCE_STAGES,
    AssignmentCreate,
    EvidenceCreate,
    EvidenceFile,
    IncidentCreate,
    IncidentFilters,
    IncidentUpdateCreate,
)

log = logging.getLogger("sentinelloop.database")

_STAGE_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "application/pdf",
        "text/plain",
    }
)


def _dump(model, *, exclude_unset: bool = False) -> dict:
    return model.model_dump(mode="json", exclude_unset=exclude_unset, exclude_none=True)


def _first_row(data: object, operation: str) -> dict:
    if not data or not isinstance(data, list):
        raise PersistenceError(f"{operation} returned no rows")
    row = data[0]
    if not isinstance(row, dict):
        raise PersistenceError(f"{operation} returned an unexpected row shape")
    return row


def _execute(builder, operation: str):
    try:
        return builder.execute()
    except APIError as exc:
        raise PersistenceError(f"{operation} failed") from exc


def _safe_stage(stage: str) -> str:
    cleaned = _STAGE_RE.sub("", stage.strip().lower().replace(" ", "_"))
    if not cleaned:
        raise PersistenceError("evidence stage is empty after sanitization")
    return cleaned


def _safe_extension(filename: str | None) -> str:
    if not filename:
        return ""
    suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
    if not suffix or len(suffix) > 12:
        return ""
    if not re.fullmatch(r"\.[a-z0-9]+", suffix):
        return ""
    return suffix


def evidence_storage_path(incident_id: UUID, stage: str, filename: str | None) -> str:
    """Collision-resistant object key: <incident_id>/<stage>/<uuid><ext>."""
    return f"{incident_id}/{_safe_stage(stage)}/{uuid4().hex}{_safe_extension(filename)}"


def _as_evidence_file(
    file: EvidenceFile | bytes,
    *,
    filename: str | None,
    content_type: str | None,
) -> EvidenceFile:
    if isinstance(file, EvidenceFile):
        return file
    return EvidenceFile(content=file, filename=filename, content_type=content_type)


class IncidentRepository:
    """Typed persistence operations. Pass a mock Client in unit tests."""

    def __init__(
        self,
        client: Client | None = None,
        *,
        storage_bucket: str | None = None,
    ) -> None:
        self._client = client or get_supabase_client()
        self._bucket = storage_bucket or evidence_bucket_name()

    def create_incident(self, data: IncidentCreate) -> Incident:
        payload = _dump(data)
        log.info("create_incident table=incidents incident_ref=%s", data.incident_ref)
        response = _execute(self._client.table("incidents").insert(payload), "create_incident")
        return Incident.model_validate(_first_row(response.data, "create_incident"))

    def get_incident(self, incident_id: UUID) -> Incident | None:
        response = _execute(
            self._client.table("incidents").select("*").eq("id", str(incident_id)).limit(1),
            "get_incident",
        )
        rows = response.data or []
        if not rows:
            return None
        return Incident.model_validate(rows[0])

    def list_incidents(self, filters: IncidentFilters | None = None) -> list[Incident]:
        filters = filters or IncidentFilters()
        query = self._client.table("incidents").select("*")
        if filters.status is not None:
            query = query.eq("status", filters.status)
        if filters.current_risk_level is not None:
            query = query.eq("current_risk_level", filters.current_risk_level)
        if filters.hazard_category is not None:
            query = query.eq("hazard_category", filters.hazard_category)
        if filters.detected_language is not None:
            query = query.eq("detected_language", filters.detected_language)
        if filters.reporter_id is not None:
            query = query.eq("reporter_id", filters.reporter_id)
        if filters.created_after is not None:
            query = query.gte("created_at", filters.created_after.isoformat())
        if filters.created_before is not None:
            query = query.lte("created_at", filters.created_before.isoformat())
        end = filters.offset + filters.limit - 1
        query = query.order("created_at", desc=True).range(filters.offset, end)
        response = _execute(query, "list_incidents")
        return [Incident.model_validate(row) for row in (response.data or [])]

    def update_incident_status(self, incident_id: UUID, status: str) -> Incident:
        log.info("update_incident_status incident_id=%s status=%s", incident_id, status)
        response = _execute(
            self._client.table("incidents").update({"status": status}).eq("id", str(incident_id)),
            "update_incident_status",
        )
        if not response.data:
            raise RecordNotFoundError(f"incident not found: {incident_id}")
        return Incident.model_validate(_first_row(response.data, "update_incident_status"))

    def update_incident_fields(self, incident_id: UUID, fields: dict) -> Incident:
        allowed = {
            "status",
            "resolved_at",
            "closed_at",
            "reopen_count",
            "hazard_category",
            "hazard_description",
            "location",
            "injury_occurred",
            "hazard_currently_active",
            "people_exposed",
            "current_risk_level",
            "session_id",
            "detected_language",
            "original_message_text",
            "duplicate_of",
            "site_id",
        }
        payload = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not payload:
            raise PersistenceError("update_incident_fields requires at least one allowed field")
        log.info("update_incident_fields incident_id=%s keys=%s", incident_id, sorted(payload))
        response = _execute(
            self._client.table("incidents").update(payload).eq("id", str(incident_id)),
            "update_incident_fields",
        )
        if not response.data:
            raise RecordNotFoundError(f"incident not found: {incident_id}")
        return Incident.model_validate(_first_row(response.data, "update_incident_fields"))

    def add_update(self, data: IncidentUpdateCreate) -> IncidentUpdate:
        payload = _dump(data)
        log.info("add_update table=incident_updates type=%s", data.update_type)
        response = _execute(
            self._client.table("incident_updates").insert(payload),
            "add_update",
        )
        return IncidentUpdate.model_validate(_first_row(response.data, "add_update"))

    def assign_incident(self, data: AssignmentCreate) -> Assignment:
        payload = _dump(data)
        log.info("assign_incident table=assignments incident_id=%s", data.incident_id)
        response = _execute(self._client.table("assignments").insert(payload), "assign_incident")
        return Assignment.model_validate(_first_row(response.data, "assign_incident"))

    def get_assignment_for_incident(self, incident_id: UUID) -> Assignment | None:
        response = _execute(
            self._client.table("assignments")
            .select("*")
            .eq("incident_id", str(incident_id))
            .order("created_at", desc=True)
            .limit(1),
            "get_assignment_for_incident",
        )
        rows = response.data or []
        if not rows:
            return None
        return Assignment.model_validate(rows[0])

    def update_assignment(self, assignment_id: UUID, fields: dict) -> Assignment:
        allowed = {"team", "slack_channel_id", "assigned_to", "assignment_status", "acknowledged_at", "completed_at"}
        payload = {key: value for key, value in fields.items() if key in allowed and value is not None}
        if not payload:
            raise PersistenceError("update_assignment requires at least one allowed field")
        response = _execute(
            self._client.table("assignments").update(payload).eq("id", str(assignment_id)),
            "update_assignment",
        )
        if not response.data:
            raise RecordNotFoundError(f"assignment not found: {assignment_id}")
        return Assignment.model_validate(_first_row(response.data, "update_assignment"))

    def add_evidence(
        self,
        file: EvidenceFile | bytes,
        incident_id: UUID,
        stage: str,
        *,
        metadata: EvidenceCreate | None = None,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> IncidentEvidence:
        if stage not in EVIDENCE_STAGES:
            raise PersistenceError(f"unsupported evidence stage {stage!r}; expected one of {sorted(EVIDENCE_STAGES)}")
        if self.get_incident(incident_id) is None:
            raise RecordNotFoundError(f"incident not found: {incident_id}")

        evidence_file = _as_evidence_file(file, filename=filename, content_type=content_type)
        if not evidence_file.content:
            raise EvidenceUploadError("evidence file is empty")
        mime = evidence_file.content_type or content_type
        if mime and mime not in _ALLOWED_CONTENT_TYPES:
            raise EvidenceUploadError(f"unsupported evidence content type: {mime}")

        path = evidence_storage_path(incident_id, stage, evidence_file.filename or filename)
        file_options: FileOptions | None = None
        if mime:
            file_options = {"content-type": mime}
        log.info(
            "add_evidence upload bucket=%s path=%s incident_id=%s",
            self._bucket,
            path,
            incident_id,
        )
        try:
            self._client.storage.from_(self._bucket).upload(path, evidence_file.content, file_options)
        except Exception as exc:
            raise EvidenceUploadError("evidence storage upload failed") from exc

        try:
            url = self._client.storage.from_(self._bucket).get_public_url(path)
        except Exception:
            url = path
        if not isinstance(url, str) or not url:
            url = path

        row: dict = {
            "incident_id": str(incident_id),
            "stage": stage,
            "storage_reference": url,
        }
        extra = _dump(metadata) if metadata is not None else {}
        row.update(extra)
        try:
            response = _execute(
                self._client.table("incident_evidence").insert(row),
                "add_evidence",
            )
        except PersistenceError as exc:
            self._remove_storage_object(path)
            raise PartialPersistenceError("evidence uploaded but incident_evidence insert failed") from exc
        return IncidentEvidence.model_validate(_first_row(response.data, "add_evidence"))

    def increment_duplicate_count(self, incident_id: UUID) -> Incident:
        """Increment incidents.duplicate_count with optimistic concurrency.

        No increment RPC was found in the available schema sources. This
        compare-and-set uses the existing column only (no migrations).
        """
        for _ in range(3):
            current = self.get_incident(incident_id)
            if current is None:
                raise RecordNotFoundError(f"incident not found: {incident_id}")
            previous = current.duplicate_count or 0
            nxt = previous + 1
            response = _execute(
                self._client.table("incidents")
                .update({"duplicate_count": nxt})
                .eq("id", str(incident_id))
                .eq("duplicate_count", previous),
                "increment_duplicate_count",
            )
            if response.data:
                return Incident.model_validate(_first_row(response.data, "increment_duplicate_count"))
        raise PersistenceError("increment_duplicate_count lost a concurrent update")

    def _remove_storage_object(self, path: str) -> None:
        try:
            self._client.storage.from_(self._bucket).remove([path])
        except Exception:
            log.exception("failed to remove orphaned evidence object path=%s", path)


_default_repo: IncidentRepository | None = None


def _repo() -> IncidentRepository:
    global _default_repo
    if _default_repo is None:
        _default_repo = IncidentRepository()
    return _default_repo


def reset_default_repository() -> None:
    global _default_repo
    _default_repo = None


def create_incident(data: IncidentCreate) -> Incident:
    return _repo().create_incident(data)


def get_incident(incident_id: UUID) -> Incident | None:
    return _repo().get_incident(incident_id)


def list_incidents(filters: IncidentFilters | None = None) -> list[Incident]:
    return _repo().list_incidents(filters)


def update_incident_status(incident_id: UUID, status: str) -> Incident:
    return _repo().update_incident_status(incident_id, status)


def update_incident_fields(incident_id: UUID, fields: dict) -> Incident:
    return _repo().update_incident_fields(incident_id, fields)


def add_update(data: IncidentUpdateCreate) -> IncidentUpdate:
    return _repo().add_update(data)


def assign_incident(data: AssignmentCreate) -> Assignment:
    return _repo().assign_incident(data)


def get_assignment_for_incident(incident_id: UUID) -> Assignment | None:
    return _repo().get_assignment_for_incident(incident_id)


def update_assignment(assignment_id: UUID, fields: dict) -> Assignment:
    return _repo().update_assignment(assignment_id, fields)


def add_evidence(
    file: EvidenceFile | bytes,
    incident_id: UUID,
    stage: str,
    *,
    metadata: EvidenceCreate | None = None,
    filename: str | None = None,
    content_type: str | None = None,
) -> IncidentEvidence:
    return _repo().add_evidence(
        file,
        incident_id,
        stage,
        metadata=metadata,
        filename=filename,
        content_type=content_type,
    )


def increment_duplicate_count(incident_id: UUID) -> Incident:
    return _repo().increment_duplicate_count(incident_id)
