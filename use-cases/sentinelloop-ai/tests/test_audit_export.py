"""Read-only audit-export API tests. No live Supabase, OpenRouter, or webhooks."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from dashboard.schemas import AUDIT_EXPORT_VERSION
from database.repository import IncidentRepository
from database.schemas import AssignmentCreate, IncidentUpdateCreate
from tests.test_database import FakeBackend, _create_payload

_REQUIRED_KEYS = (
    "incident_information",
    "original_report",
    "language_processing",
    "extracted_information",
    "ai_decision",
    "risk_analysis",
    "guidance_history",
    "coordination_history",
    "assignment_history",
    "incident_timeline",
    "resolution",
    "audit_metadata",
)


def _app(repo: IncidentRepository, ledger_path=None) -> TestClient:
    handler = DashboardHandler(repository=repo, ledger_path=ledger_path)
    app = FastAPI()
    app.include_router(handler.get_router())
    return TestClient(app)


def _seed_audit(repo: IncidentRepository, backend: FakeBackend) -> object:
    now = datetime.now(timezone.utc)
    earlier = now - timedelta(minutes=12)
    later = now - timedelta(minutes=4)
    raw = "[LOC:Bay 4|Hydraulic Press] இயந்திரம் எண்ணெய் கசிகிறது"
    incident = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000088",
            hazard_category="chemical",
            hazard_description="Oil leak near hydraulic press",
            location="Bay 4",
            status="RESOLVED",
            current_risk_level="Critical",
            reporter_id="+94771234567",
            detected_language="ta",
            original_message_text=raw,
            session_id="sess-audit-88",
            people_exposed=6,
            hazard_currently_active=True,
        )
    )
    for row in backend.tables["incidents"]:
        if row["incident_ref"] == "SL-2026-000088":
            row["created_at"] = earlier.isoformat()
            row["resolved_at"] = now.isoformat()
            row["duplicate_count"] = 3
    repo.assign_incident(
        AssignmentCreate(
            incident_id=incident.id, assigned_to="N. Fernando", team="HazMat", assignment_status="assigned"
        )
    )
    for row in backend.tables["assignments"]:
        row["assigned_at"] = later.isoformat()
    backend.tables["risk_assessments"].append(
        {
            "id": str(uuid4()),
            "incident_id": str(incident.id),
            "severity": 5,
            "severity_reason": "Flammable material at an active machine.",
            "likelihood": 4,
            "likelihood_reason": "Leak already visible to workers.",
            "risk_score": 20,
            "base_risk_level": "High",
            "final_risk_level": "Critical",
            "applied_overrides": ["active_critical_category"],
            "created_at": later.isoformat(),
        }
    )
    first = repo.add_update(
        IncidentUpdateCreate(
            incident_id=incident.id,
            update_type="incident_created",
            new_status="REPORTED",
            actor_type="system",
            actor_reference="whatsapp_orchestrator",
            message="Report received",
        )
    )
    guidance = repo.add_update(
        IncidentUpdateCreate(
            incident_id=incident.id,
            update_type="guidance_sent",
            actor_type="agent",
            actor_reference="guidance_agent",
            message="Turn off machine immediately",
            metadata={
                "guidance": "Turn off machine immediately",
                "language": "en",
                "source_document": "Electrical Safety Manual",
                "section": "Section 4.2",
                "line_reference": "Section 4.2",
                "matched_text": "Isolate energy before approaching the leak.",
                "source_id": "electrical_12",
                "api_key": "sk-should-never-leak",
            },
        )
    )
    coord = repo.add_update(
        IncidentUpdateCreate(
            incident_id=incident.id,
            update_type="slack_coordination_completed",
            actor_type="agent",
            actor_reference="coordination_agent",
            message="Officer notified",
            metadata={"source": "slack", "channel": "Slack"},
        )
    )
    closed = repo.add_update(
        IncidentUpdateCreate(
            incident_id=incident.id,
            update_type="incident_closed",
            new_status="CLOSED",
            actor_type="safety_officer",
            actor_reference="N. Fernando",
            message="Worker confirmed the area is safe.",
        )
    )
    times = {
        str(first.id): earlier.isoformat(),
        str(guidance.id): (earlier + timedelta(minutes=3)).isoformat(),
        str(coord.id): later.isoformat(),
        str(closed.id): now.isoformat(),
    }
    for row in backend.tables["incident_updates"]:
        stamp = times.get(str(row.get("id")))
        if stamp:
            row["created_at"] = stamp
    backend.tables["incident_evidence"].append(
        {
            "id": str(uuid4()),
            "incident_id": str(incident.id),
            "stage": "verification",
            "evidence_type": "image/jpeg",
            "storage_reference": "https://example.supabase.co/storage/v1/object/public/evidence/after.jpg",
            "caption_or_description": "Cleaned floor",
            "created_at": now.isoformat(),
        }
    )
    return incident


def test_audit_export_missing_incident():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    client = _app(repo)
    missing = client.get("/api/incidents/does-not-exist/audit-export")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "incident not found"


def test_audit_export_complete_structure(tmp_path, monkeypatch):
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    incident = _seed_audit(repo, backend)
    monkeypatch.setenv("OPENROUTER_BUDGET_CEILING_USD", "3")
    ledger = tmp_path / "spend_ledger.json"
    created = datetime.now(timezone.utc) - timedelta(minutes=10)
    ledger.write_text(
        json.dumps(
            {
                "cumulative_spend_usd": "0.08",
                "recent_calls": [
                    {
                        "timestamp": created.isoformat(),
                        "model": "qwen/qwen3-32b:free",
                        "model_role": "role_fast",
                        "session_id": "sess-audit-88",
                        "latency_s": 0.4,
                        "cost_usd": "0.04",
                        "api_key": "sk-should-never-leak",
                    },
                    {
                        "timestamp": created.isoformat(),
                        "model": "qwen/qwen3-32b:free",
                        "model_role": "role_reasoning",
                        "incident_ref": "SL-2026-000088",
                        "cost_usd": "0.04",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    client = _app(repo, ledger_path=ledger)
    response = client.get("/api/incidents/SL-2026-000088/audit-export")
    assert response.status_code == 200
    body = response.json()
    dumped = json.dumps(body)
    assert "sk-should-never-leak" not in dumped
    assert "+94771234567" not in dumped
    assert "••••" in body["original_report"]["worker_identifier"]
    for key in _REQUIRED_KEYS:
        assert key in body
    info = body["incident_information"]
    assert info["incident_id"] == "SL-2026-000088"
    assert info["equipment"] == "Hydraulic Press"
    assert info["duplicate_count"] == 3
    assert info["current_risk_level"] == "CRITICAL"
    report = body["original_report"]
    assert report["source"] == "WhatsApp"
    assert report["message"].startswith("[LOC:Bay 4|Hydraulic Press]")
    assert "எண்ணெய்" in report["message"]
    language = body["language_processing"]
    assert language["language"] == "Tamil"
    assert language["detected_language"] == "ta"
    assert language["translated_text"] == "Oil leak near hydraulic press"
    fields = {row["field"]: row for row in body["extracted_information"]["fields"]}
    assert fields["equipment"]["value"] == "Hydraulic Press"
    assert fields["equipment"]["confidence"] == 1.0
    ai = body["ai_decision"]
    assert ai["severity"] == "CRITICAL"
    assert ai["likelihood"] == "LIKELY"
    assert ai["confidence"] is not None
    assert "Flammable" in (ai["reasoning_summary"] or "")
    risk = body["risk_analysis"]
    assert risk["score"] == 20
    assert risk["explanation"]
    assert "Deterministic engine" in (risk["rule_validation"] or "")
    guidance = body["guidance_history"]
    assert guidance
    assert guidance[0]["source"] == "Electrical Safety Manual"
    assert guidance[0]["line_reference"] == "Section 4.2"
    assert guidance[0]["rule_id"] == "electrical_12"
    assert body["coordination_history"]
    assert body["coordination_history"][0]["channel"] == "Slack"
    assert body["assignment_history"]
    assert body["assignment_history"][0]["officer"]
    times = [row["time"] for row in body["incident_timeline"] if row["time"]]
    assert times == sorted(times)
    assert {row["update_type"] for row in body["incident_timeline"]} >= {
        "incident_created",
        "guidance_sent",
        "slack_coordination_completed",
    }
    resolution = body["resolution"]
    assert resolution["status"] in {"Resolved", "Closed", "RESOLVED", "CLOSED"}
    assert resolution["evidence"]
    meta = body["audit_metadata"]
    assert meta["audit_export_version"] == AUDIT_EXPORT_VERSION
    assert meta["audit_hash"]
    assert "role_fast" in meta["models_used"]
    assert meta["ai_calls"] == 2
    assert meta["estimated_cost"] == "$0.08"
    by_uuid = client.get(f"/api/incidents/{incident.id}/audit-export")
    assert by_uuid.status_code == 200
    assert by_uuid.json()["incident_information"]["incident_id"] == "SL-2026-000088"


def test_audit_export_rejects_writes():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    _seed_audit(repo, backend)
    client = _app(repo)
    response = client.post("/api/incidents/SL-2026-000088/audit-export")
    assert response.status_code == 405
    assert response.json()["detail"] == "dashboard is read-only"


def test_audit_hash_changes_when_content_changes():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    _seed_audit(repo, backend)
    client = _app(repo)
    first = client.get("/api/incidents/SL-2026-000088/audit-export").json()
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=repo.get_incident_by_ref("SL-2026-000088").id,
            update_type="status_transition",
            message="Note added after first export",
        )
    )
    second = client.get("/api/incidents/SL-2026-000088/audit-export").json()
    assert first["audit_metadata"]["audit_hash"] != second["audit_metadata"]["audit_hash"]
