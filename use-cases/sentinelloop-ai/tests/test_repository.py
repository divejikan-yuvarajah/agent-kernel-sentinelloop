"""Repository persistence tests using the in-memory FakeBackend. No live Supabase."""

from __future__ import annotations

from uuid import uuid4

from database.exceptions import RecordNotFoundError
from database.repository import IncidentRepository
from database.schemas import EvidenceFile
from tests.test_database import FakeBackend, _create_payload


def test_create_and_get_incident_round_trip():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    created = repo.create_incident(_create_payload(incident_ref="SL-2026-000501", location="Bay 9"))
    fetched = repo.get_incident(created.id)
    assert fetched is not None
    assert fetched.incident_ref == "SL-2026-000501"
    assert fetched.location == "Bay 9"
    assert fetched.duplicate_count == 0


def test_missing_incident_returns_none():
    repo = IncidentRepository(FakeBackend(), storage_bucket="evidence")
    assert repo.get_incident(uuid4()) is None


def test_increment_duplicate_count_persists():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    created = repo.create_incident(_create_payload(incident_ref="SL-2026-000502"))
    updated = repo.increment_duplicate_count(created.id)
    assert updated.duplicate_count == 1
    again = repo.increment_duplicate_count(created.id)
    assert again.duplicate_count == 2


def test_status_update_is_recorded():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    created = repo.create_incident(_create_payload(incident_ref="SL-2026-000503"))
    repo.update_incident_status(created.id, "IN_PROGRESS")
    fetched = repo.get_incident(created.id)
    assert fetched is not None
    assert fetched.status == "IN_PROGRESS"


def test_timeline_update_and_evidence_link():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    created = repo.create_incident(_create_payload(incident_ref="SL-2026-000504"))
    evidence = repo.add_evidence(
        EvidenceFile(content=b"jpeg-bytes", filename="photo.jpg", content_type="image/jpeg"),
        created.id,
        "report",
    )
    assert evidence is not None
    assert str(evidence.incident_id) == str(created.id)
    assert evidence.stage == "report"


def test_unknown_increment_raises():
    repo = IncidentRepository(FakeBackend(), storage_bucket="evidence")
    try:
        repo.increment_duplicate_count(uuid4())
    except (RecordNotFoundError, KeyError, Exception) as exc:
        assert exc is not None
    else:
        raise AssertionError("expected missing incident to fail")
