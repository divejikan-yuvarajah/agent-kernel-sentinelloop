"""Scripted AI pipeline used by DEMO_MODE and the end-to-end smoke test.

Calls the real ``calculate_risk()`` matrix. Does not require OpenRouter,
Telegram, or Slack credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from database.models import Incident
from database.schemas import IncidentCreate
from integrations.incident_orchestrator import IncidentOrchestrator
from tools.risk_tools import calculate_risk, normalize_category


class Box:
    def __init__(self, **kwargs) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_dump(self, *args, **kwargs):
        del args, kwargs
        return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}

    def worker_text(self) -> str:
        return getattr(self, "text", "Move away from the hazard and notify a supervisor.")


class Scripted:
    def __init__(self, name: str, responses: list | None = None, default=None) -> None:
        self.name = name
        self.responses = list(responses or [])
        self.default = default
        self.calls: list[tuple] = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.responses:
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if callable(self.default) and not isinstance(self.default, Box):
            return self.default(*args, **kwargs)
        return self.default


class FakeCoord:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.fail = False
        self.posted = True

    async def coordinate_incident(self, incident):
        payload = incident if isinstance(incident, dict) else incident.model_dump()
        self.calls.append(payload)
        if self.fail:
            return Box(posted=False, coordination_error="slack_unavailable", slack_message_ts=None)
        return Box(
            posted=self.posted,
            slack_channel_id="C-DEMO",
            slack_message_ts="1.0",
            slack_thread_ts="1.0",
            assigned_team="Electrical Maintenance",
            coordination_error=None,
        )


class MemoryRepo:
    def __init__(self) -> None:
        self.incidents: dict[UUID, dict] = {}
        self.by_ref: dict[str, UUID] = {}
        self.create_calls: list[IncidentCreate] = []
        self.updates: list = []
        self.evidence: list = []
        self.assignments: dict[UUID, Any] = {}
        self.fail_create = False

    def create_incident(self, data: IncidentCreate) -> Incident:
        if self.fail_create:
            from database.exceptions import PersistenceError

            raise PersistenceError("create failed")
        self.create_calls.append(data)
        uid = uuid4()
        row = {
            "id": uid,
            "incident_ref": data.incident_ref,
            "reporter_id": data.reporter_id,
            "source_channel": data.source_channel,
            "status": data.status,
            "duplicate_count": 0,
            "hazard_category": data.hazard_category,
            "hazard_description": data.hazard_description,
            "location": data.location,
            "session_id": data.session_id,
            "detected_language": data.detected_language,
            "original_message_id": data.original_message_id,
            "original_message_text": data.original_message_text,
            "injury_occurred": data.injury_occurred,
            "hazard_currently_active": data.hazard_currently_active,
            "people_exposed": data.people_exposed,
            "current_risk_level": data.current_risk_level,
            "input_method": data.input_method,
            "created_by": data.created_by,
            "source_metadata": data.source_metadata,
            "pipeline_version": data.pipeline_version,
            "created_at": datetime.now(timezone.utc),
        }
        self.incidents[uid] = row
        self.by_ref[data.incident_ref] = uid
        return Incident.model_validate(row)

    def get_incident(self, incident_id: UUID) -> Incident | None:
        row = self.incidents.get(incident_id)
        return Incident.model_validate(row) if row else None

    def get_incident_by_ref(self, incident_ref: str) -> Incident | None:
        uid = self.by_ref.get(incident_ref)
        return self.get_incident(uid) if uid else None

    def list_incidents(self, filters=None):
        del filters
        return [Incident.model_validate(row) for row in self.incidents.values()]

    def list_all_incidents(self, filters=None):
        return self.list_incidents(filters)

    def add_update(self, data) -> None:
        self.updates.append(data)

    def add_evidence(self, file, incident_id, stage, *, metadata=None, filename=None, content_type=None):
        self.evidence.append(
            {
                "incident_id": incident_id,
                "stage": stage,
                "filename": filename,
                "content_type": content_type,
                "source": getattr(metadata, "source", None) if metadata is not None else None,
            }
        )
        return SimpleNamespace(id=uuid4(), incident_id=incident_id)

    def assign_incident(self, data):
        record = SimpleNamespace(
            id=uuid4(),
            incident_id=data.incident_id,
            team=data.team,
            assigned_to=data.assigned_to,
            assignment_status=data.assignment_status,
            assigned_at=datetime.now(timezone.utc),
        )
        self.assignments[data.incident_id] = record
        return record

    def get_assignment_for_incident(self, incident_id: UUID):
        return self.assignments.get(incident_id)

    def update_incident_status(self, incident_id: UUID, status: str) -> Incident:
        self.incidents[incident_id]["status"] = status
        return Incident.model_validate(self.incidents[incident_id])

    def increment_duplicate_count(self, incident_id: UUID) -> Incident:
        self.incidents[incident_id]["duplicate_count"] = (
            int(self.incidents[incident_id].get("duplicate_count") or 0) + 1
        )
        return Incident.model_validate(self.incidents[incident_id])


class RecordingTelegram:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def send_text_message(self, *args, **kwargs):
        self.calls.append(("text", args, kwargs))
        return {"ok": True}

    async def send_guidance(self, *args, **kwargs):
        self.calls.append(("guidance", args, kwargs))
        return {"ok": True}

    async def send_clarification(self, *args, **kwargs):
        self.calls.append(("clarification", args, kwargs))
        return {"ok": True}

    async def send_verification_prompt(self, *args, **kwargs):
        self.calls.append(("verify", args, kwargs))
        return {"ok": True}


def scripted_intake(raw_text: str = "There is smoke coming from machine 4. Three workers are nearby.") -> Box:
    return Box(
        raw_text=raw_text,
        translated_text=raw_text,
        language="en",
        is_hazard_report=True,
        qr_location=None,
        session_id="dashboard:officer",
        message_type="text",
        clean_text=raw_text,
    )


def scripted_incident(
    category: str = "fire/smoke",
    location: str = "Machine 4",
    people_exposed: int = 3,
    is_active: bool = True,
    already_injured: bool = False,
    raw_text: str = "There is smoke coming from machine 4. Three workers are nearby.",
) -> Box:
    return Box(
        hazard_category=category,
        location=location,
        equipment_involved="machine 4",
        people_exposed=people_exposed,
        is_active=is_active,
        already_injured=already_injured,
        has_image=False,
        needs_clarification=False,
        skip_clarification=True,
        clarification_question=None,
        qr_location=location,
        qr_equipment=None,
        raw_text=raw_text,
        translated_text=raw_text,
        language="en",
    )


def scripted_guidance() -> Box:
    return Box(
        text="Move away from the machine and notify a supervisor.\n\nDo not attempt to fight the smoke.",
        knowledge_grounded=True,
    )


async def scripted_risk(incident, session=None):
    del session
    data = (
        incident if isinstance(incident, dict) else getattr(incident, "model_dump", lambda: dict(incident.__dict__))()
    )
    category = str(data.get("hazard_category") or data.get("category") or "fire/smoke")
    people = data.get("people_exposed")
    try:
        people_n = int(people) if people is not None else 3
    except (TypeError, ValueError):
        people_n = 3
    active = data.get("is_active")
    if active is None:
        active = data.get("hazard_currently_active")
    injured = data.get("already_injured")
    if injured is None:
        injured = data.get("injury_occurred")
    result = calculate_risk(
        severity=5,
        likelihood=4,
        active=bool(True if active is None else active),
        people_exposed=people_n,
        category=normalize_category(category) or category,
        already_injured=bool(injured),
    )
    return Box(
        level=result["level"],
        score=result["score"],
        explanation=result.get("explanation") or result.get("rationale") or "Deterministic risk matrix",
        severity=5,
        likelihood=4,
    )


def build_demo_orchestrator(
    *,
    repository: Any | None = None,
    raw_text: str = "There is smoke coming from machine 4. Three workers are nearby.",
    category: str = "fire/smoke",
    location: str = "Machine 4",
    people_exposed: int = 3,
    is_active: bool = True,
    already_injured: bool = False,
) -> IncidentOrchestrator:
    from agentkernel.core.session.in_memory import InMemorySessionStore

    from tools.duplicate_tools import DuplicateResult

    repo = repository if repository is not None else MemoryRepo()
    coord = FakeCoord()
    orch = IncidentOrchestrator(
        repository=repo,
        telegram=RecordingTelegram(),
        coordination=coord,
        intake_fn=Scripted("intake", default=scripted_intake(raw_text)),
        duplicate_fn=lambda query, repository=None: DuplicateResult(status="none", action="create_new"),
        incident_fn=Scripted(
            "incident",
            default=scripted_incident(
                category=category,
                location=location,
                people_exposed=people_exposed,
                is_active=is_active,
                already_injured=already_injured,
                raw_text=raw_text,
            ),
        ),
        risk_fn=scripted_risk,
        guidance_fn=Scripted("guidance", default=scripted_guidance()),
        session_store=InMemorySessionStore(),
        emergency_fn=lambda raw: False,
    )
    orch._repo = repo
    orch._coord = coord
    return orch
