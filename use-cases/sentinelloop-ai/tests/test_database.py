"""Unit tests for the SentinelLoop persistence layer. No live Supabase."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from postgrest.exceptions import APIError
from pydantic import ValidationError

from database.client import DatabaseConfigError, create_supabase_client, reset_supabase_client
from database.exceptions import EvidenceUploadError, PartialPersistenceError, RecordNotFoundError
from database.models import Incident, IncidentEvidence
from database.repository import IncidentRepository, evidence_storage_path
from database.schemas import AssignmentCreate, EvidenceFile, IncidentCreate, IncidentFilters, IncidentUpdateCreate


class FakeResponse:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, backend: "FakeBackend", table: str):
        self.backend = backend
        self.table = table
        self.op = "select"
        self.payload = None
        self.filters: dict[str, object] = {}
        self.limit_n = None
        self.order_by = None
        self.range_span = None

    def insert(self, payload):
        self.op = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.op = "update"
        self.payload = payload
        return self

    def delete(self):
        self.op = "delete"
        return self

    def select(self, *_cols):
        if self.op not in {"update", "delete"}:
            self.op = "select"
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def in_(self, key, values):
        self.filters[f"in:{key}"] = list(values)
        return self

    def gte(self, key, value):
        self.filters[f"gte:{key}"] = value
        return self

    def lte(self, key, value):
        self.filters[f"lte:{key}"] = value
        return self

    def order(self, column, desc=False):
        self.order_by = (column, desc)
        return self

    def range(self, start, end):
        self.range_span = (start, end)
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self):
        return self.backend.execute(self)


class FakeBucket:
    def __init__(self, backend: "FakeBackend", name: str):
        self.backend = backend
        self.name = name

    def upload(self, path, file, file_options=None):
        if self.backend.fail_upload:
            raise RuntimeError("upload failed")
        self.backend.uploads.append({"bucket": self.name, "path": path, "file": file, "options": file_options})
        return type("UploadResponse", (), {"path": path, "full_path": path, "fullPath": path})()

    def get_public_url(self, path):
        return f"https://example.supabase.co/storage/v1/object/public/{self.name}/{path}"

    def remove(self, paths):
        self.backend.removes.extend(paths)
        return []


class FakeStorage:
    def __init__(self, backend: "FakeBackend"):
        self.backend = backend

    def from_(self, name):
        return FakeBucket(self.backend, name)


class FakeBackend:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {
            "incidents": [],
            "incident_evidence": [],
            "assignments": [],
            "incident_updates": [],
            "risk_assessments": [],
            "handover_summaries": [],
        }
        self.uploads: list[dict] = []
        self.removes: list[str] = []
        self.fail_upload = False
        self.fail_evidence_insert = False
        self.last_query: FakeQuery | None = None
        self.storage = FakeStorage(self)

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def _new_row(self, payload: dict) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        row = dict(payload)
        row.setdefault("id", str(uuid4()))
        row.setdefault("created_at", now)
        row.setdefault("updated_at", now)
        return row

    def execute(self, query: FakeQuery) -> FakeResponse:
        self.last_query = query
        rows = self.tables.setdefault(query.table, [])
        if query.op == "insert":
            if query.table == "incident_evidence" and self.fail_evidence_insert:
                raise APIError({"message": "insert failed", "code": "23503", "hint": None, "details": None})
            row = self._new_row(query.payload)
            if query.table == "incidents":
                row.setdefault("duplicate_count", 0)
                row.setdefault("status", "REPORTED")
            rows.append(row)
            return FakeResponse([row])
        matched = rows
        for key, value in query.filters.items():
            if key.startswith("gte:"):
                field = key[4:]
                matched = [r for r in matched if str(r.get(field) or "") >= str(value)]
            elif key.startswith("lte:"):
                field = key[4:]
                matched = [r for r in matched if str(r.get(field) or "") <= str(value)]
            elif key.startswith("in:"):
                field = key[3:]
                allowed = {str(item) for item in value}
                matched = [r for r in matched if str(r.get(field)) in allowed]
            else:
                matched = [r for r in matched if str(r.get(key)) == str(value)]
        if query.op == "update":
            if not matched:
                return FakeResponse([])
            updated = []
            for row in matched:
                row.update(query.payload)
                updated.append(dict(row))
            return FakeResponse(updated)
        if query.op == "delete":
            ids = {id(row) for row in matched}
            self.tables[query.table][:] = [row for row in rows if id(row) not in ids]
            return FakeResponse(list(matched))
        if query.order_by:
            column, desc = query.order_by
            matched = sorted(matched, key=lambda r: r.get(column) or "", reverse=bool(desc))
        if query.range_span is not None:
            start, end = query.range_span
            matched = matched[start : end + 1]
        if query.limit_n is not None:
            matched = matched[: query.limit_n]
        return FakeResponse(list(matched))


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def repo(backend: FakeBackend) -> IncidentRepository:
    return IncidentRepository(backend, storage_bucket="evidence")


def _create_payload(**overrides) -> IncidentCreate:
    data = {
        "incident_ref": "SL-2026-000001",
        "reporter_id": "whatsapp:+94770000000",
        "hazard_description": "Exposed cable",
        "hazard_category": "electrical",
    }
    data.update(overrides)
    return IncidentCreate.model_validate(data)


def test_incident_model_duplicate_count_default():
    incident = Incident.model_validate(
        {
            "id": str(uuid4()),
            "incident_ref": "SL-2026-000002",
            "reporter_id": "r1",
            "source_channel": "whatsapp",
            "status": "REPORTED",
        }
    )
    assert incident.duplicate_count == 0


def test_incident_model_unknown_injury_is_none():
    incident = Incident.model_validate(
        {
            "id": str(uuid4()),
            "incident_ref": "SL-2026-000003",
            "reporter_id": "r1",
            "source_channel": "whatsapp",
            "status": "OPEN",
            "injury_occurred": "unknown",
        }
    )
    assert incident.injury_occurred is None


def test_incident_model_rejects_invalid_uuid():
    with pytest.raises(ValidationError):
        Incident.model_validate(
            {
                "id": "not-a-uuid",
                "incident_ref": "x",
                "reporter_id": "r1",
                "source_channel": "whatsapp",
                "status": "OPEN",
            }
        )


def test_create_incident_inserts_real_columns(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    assert created.incident_ref == "SL-2026-000001"
    assert created.duplicate_count == 0
    assert backend.last_query is not None
    assert backend.last_query.table == "incidents"
    assert backend.last_query.op == "insert"
    payload = backend.last_query.payload
    assert "id" not in payload
    assert "duplicate_count" not in payload
    assert set(payload) <= {
        "incident_ref",
        "reporter_id",
        "source_channel",
        "session_id",
        "detected_language",
        "hazard_category",
        "hazard_description",
        "location",
        "injury_occurred",
        "hazard_currently_active",
        "people_exposed",
        "status",
        "current_risk_level",
        "original_message_id",
        "original_message_text",
        "site_id",
    }


def test_get_incident_found_and_missing(repo: IncidentRepository):
    created = repo.create_incident(_create_payload())
    fetched = repo.get_incident(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert repo.get_incident(uuid4()) is None


def test_list_incidents_filters_and_pagination(repo: IncidentRepository, backend: FakeBackend):
    repo.create_incident(_create_payload(incident_ref="SL-A", status="OPEN"))
    repo.create_incident(_create_payload(incident_ref="SL-B", status="CLOSED", reporter_id="other"))
    open_rows = repo.list_incidents(IncidentFilters(status="OPEN"))
    assert [row.incident_ref for row in open_rows] == ["SL-A"]
    page = repo.list_incidents(IncidentFilters(limit=1, offset=0))
    assert len(page) == 1
    assert backend.last_query is not None
    assert backend.last_query.order_by == ("created_at", True)
    assert backend.last_query.range_span == (0, 0)


def test_list_incidents_rejects_unknown_filter_fields():
    with pytest.raises(ValidationError):
        IncidentFilters.model_validate({"status": "OPEN", "sql": "drop table"})


def test_update_incident_fields_allowlist(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    updated = repo.update_incident_fields(created.id, {"status": "CLOSED", "closed_at": "2026-08-31T00:00:00+00:00"})
    assert updated.status == "CLOSED"
    assert backend.last_query is not None
    assert backend.last_query.payload["status"] == "CLOSED"
    assert "closed_at" in backend.last_query.payload


def test_update_incident_status(repo: IncidentRepository):
    created = repo.create_incident(_create_payload())
    updated = repo.update_incident_status(created.id, "ASSESSING")
    assert updated.status == "ASSESSING"


def test_update_incident_status_missing(repo: IncidentRepository):
    with pytest.raises(RecordNotFoundError):
        repo.update_incident_status(uuid4(), "OPEN")


def test_add_update_inserts_timeline(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    update = repo.add_update(
        IncidentUpdateCreate(
            incident_id=created.id,
            update_type="incident_created",
            new_status="REPORTED",
            actor_type="system",
        )
    )
    assert update.update_type == "incident_created"
    assert backend.last_query is not None
    assert backend.last_query.table == "incident_updates"


def test_assign_incident_inserts_row(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    assignment = repo.assign_incident(
        AssignmentCreate(incident_id=created.id, team="electrical", assignment_status="assigned")
    )
    assert assignment.team == "electrical"
    assert backend.last_query is not None
    assert backend.last_query.table == "assignments"


def test_add_evidence_upload_and_row(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    evidence = repo.add_evidence(
        EvidenceFile(content=b"jpeg-bytes", filename="photo.jpg", content_type="image/jpeg"),
        created.id,
        "report",
    )
    assert isinstance(evidence, IncidentEvidence)
    assert evidence.stage == "report"
    assert evidence.storage_reference.startswith("https://example.supabase.co/")
    assert backend.uploads[0]["bucket"] == "evidence"
    path = backend.uploads[0]["path"]
    assert str(created.id) in path
    assert "/report/" in path
    assert "photo.jpg" not in path
    assert ".." not in path


def test_add_evidence_upload_failure_skips_db(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    backend.fail_upload = True
    with pytest.raises(EvidenceUploadError):
        repo.add_evidence(b"x", created.id, "report", filename="a.jpg", content_type="image/jpeg")
    assert backend.tables["incident_evidence"] == []


def test_add_evidence_insert_failure_cleans_storage(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    backend.fail_evidence_insert = True
    with pytest.raises(PartialPersistenceError):
        repo.add_evidence(
            EvidenceFile(content=b"jpeg-bytes", filename="n.jpg", content_type="image/jpeg"),
            created.id,
            "report",
        )
    assert backend.removes
    assert backend.tables["incident_evidence"] == []


def test_evidence_storage_path_is_safe():
    incident_id = uuid4()
    path = evidence_storage_path(incident_id, "report", "../etc/passwd.jpg")
    assert ".." not in path
    assert path.startswith(f"{incident_id}/report/")
    assert path.endswith(".jpg")
    assert PathParts(path)


def PathParts(path: str) -> bool:
    parts = path.split("/")
    assert len(parts) == 3
    UUID(parts[0])
    return True


def test_increment_duplicate_count(repo: IncidentRepository, backend: FakeBackend):
    created = repo.create_incident(_create_payload())
    updated = repo.increment_duplicate_count(created.id)
    assert updated.duplicate_count == 1
    again = repo.increment_duplicate_count(created.id)
    assert again.duplicate_count == 2
    assert backend.last_query is not None
    assert backend.last_query.table == "incidents"
    assert backend.last_query.payload == {"duplicate_count": 2}


def test_dashboard_read_helpers(repo: IncidentRepository):
    created = repo.create_incident(_create_payload(incident_ref="SL-2026-000088"))
    assert repo.get_incident_by_ref("SL-2026-000088") is not None
    repo.add_update(IncidentUpdateCreate(incident_id=created.id, update_type="incident_created", new_status="REPORTED"))
    assert repo.list_updates_for_incident(created.id)
    assert repo.list_recent_updates(limit=5)
    assert repo.list_evidence_for_incident(created.id) == []
    assert repo.list_all_incidents()


def test_client_requires_env(monkeypatch):
    reset_supabase_client()
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(DatabaseConfigError) as exc:
        create_supabase_client()
    message = str(exc.value)
    assert "SUPABASE_URL" in message
    assert "SUPABASE_SERVICE_ROLE_KEY" in message
    assert "eyJ" not in message
