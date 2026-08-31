"""Read-only dashboard API tests. No live Supabase, OpenRouter, or webhooks."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from database.repository import IncidentRepository
from database.schemas import AssignmentCreate, IncidentUpdateCreate
from tests.test_database import FakeBackend, _create_payload


def _app(repo: IncidentRepository, ledger_path=None) -> TestClient:
    handler = DashboardHandler(repository=repo, ledger_path=ledger_path)
    app = FastAPI()
    app.include_router(handler.get_router())
    return TestClient(app)


def _seed(repo: IncidentRepository, backend: FakeBackend) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    older = now - timedelta(days=2)
    chemical = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000010",
            hazard_category="Chemical Leak",
            hazard_description="Acid spill near pump",
            location="Factory Area A",
            status="OPEN",
            current_risk_level="Critical",
            reporter_id="+94771234567",
        )
    )
    electrical = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000011",
            hazard_category="Electrical",
            hazard_description="Panel sparking",
            location="Bay 2",
            status="IN_PROGRESS",
            current_risk_level="High",
        )
    )
    resolved = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000012",
            hazard_category="Chemical Leak",
            hazard_description="Earlier leak",
            location="Factory Area A",
            status="RESOLVED",
            current_risk_level="High",
        )
    )
    again = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000013",
            hazard_category="Chemical Leak",
            hazard_description="Repeat leak",
            location="Factory Area A",
            status="ASSIGNED",
            current_risk_level="High",
        )
    )
    for row in backend.tables["incidents"]:
        if row["incident_ref"] == "SL-2026-000012":
            row["created_at"] = older.isoformat()
            row["resolved_at"] = now.isoformat()
            row["updated_at"] = now.isoformat()
        if row["incident_ref"] == "SL-2026-000010":
            row["duplicate_count"] = 3
    repo.assign_incident(
        AssignmentCreate(
            incident_id=chemical.id, assigned_to="N. Fernando", team="HazMat", assignment_status="assigned"
        )
    )
    assigned_at = (now - timedelta(minutes=18)).isoformat()
    for row in backend.tables["assignments"]:
        row["assigned_at"] = assigned_at
    backend.tables["risk_assessments"].append(
        {
            "id": str(uuid4()),
            "incident_id": str(chemical.id),
            "severity": 5,
            "severity_reason": "Active chemical leak with people nearby.",
            "likelihood": 4,
            "likelihood_reason": "Pump seal already failed.",
            "risk_score": 20,
            "base_risk_level": "High",
            "final_risk_level": "Critical",
            "applied_overrides": ["Active chemical hazard"],
            "created_at": now.isoformat(),
        }
    )
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=chemical.id,
            update_type="incident_created",
            new_status="New",
            message="Report received",
        )
    )
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=chemical.id,
            update_type="status_transition",
            previous_status="Assessed",
            new_status="Assigned",
            message="Officer assigned",
        )
    )
    return {"chemical": chemical, "electrical": electrical, "resolved": resolved, "again": again}


def test_list_incidents_filters_and_pagination():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    _seed(repo, backend)
    client = _app(repo)

    open_rows = client.get("/incidents", params={"status": "OPEN"})
    assert open_rows.status_code == 200
    body = open_rows.json()
    assert body["total"] == 1
    assert body["items"][0]["incident_id"] == "SL-2026-000010"
    assert body["items"][0]["risk_level"] == "CRITICAL"
    assert "evidence" not in body["items"][0]
    assert body["items"][0]["assigned_officer"]

    critical = client.get("/incidents", params={"risk_level": "CRITICAL"})
    assert critical.status_code == 200
    assert critical.json()["total"] == 1

    page = client.get("/incidents", params={"limit": 2, "offset": 0, "sort_by": "newest"})
    assert page.status_code == 200
    assert page.json()["limit"] == 2
    assert len(page.json()["items"]) == 2

    oldest = client.get("/incidents", params={"sort_by": "oldest"})
    ids = [row["incident_id"] for row in oldest.json()["items"]]
    assert ids[0] == "SL-2026-000012"

    riskiest = client.get("/incidents", params={"sort_by": "highest_risk"})
    assert riskiest.json()["items"][0]["risk_level"] == "CRITICAL"


def test_incident_detail_and_404():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    seeded = _seed(repo, backend)
    client = _app(repo)

    missing = client.get("/incidents/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "incident not found"

    found = client.get("/incidents/SL-2026-000010")
    assert found.status_code == 200
    payload = found.json()
    assert payload["incident_id"] == "SL-2026-000010"
    assert payload["risk"]["risk_level"] == "CRITICAL"
    assert payload["risk"]["risk_score"] == 20
    assert payload["duplicates"]["duplicate_count"] == 3
    assert payload["timeline"]
    assert "••••" in payload["reporter"]["reporter_id"]
    assert "+94771234567" not in json.dumps(payload)
    by_uuid = client.get(f"/incidents/{seeded['chemical'].id}")
    assert by_uuid.status_code == 200
    assert by_uuid.json()["incident_id"] == "SL-2026-000010"


def test_analytics_and_recurring():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    _seed(repo, backend)
    client = _app(repo)

    summary = client.get("/analytics/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["total_incidents"] == 4
    assert data["open_incidents"] == 3
    assert data["critical_incidents"] == 1
    assert data["resolved_today"] == 1
    assert data["incidents_by_risk_level"]["CRITICAL"] == 1
    assert "Chemical Leak" in data["incidents_by_category"]
    assert len(data["loop_stages"]) == 7

    recurring = client.get("/analytics/recurring")
    assert recurring.status_code == 200
    items = recurring.json()["items"]
    assert items
    chemical = next(row for row in items if row["category"] == "Chemical Leak")
    assert chemical["count"] == 3
    assert chemical["location"] == "Factory Area A"
    assert chemical["period"] == "30 days"
    assert chemical["recommendation"]


def test_router_status_hides_secrets(tmp_path, monkeypatch):
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    monkeypatch.setenv("OPENROUTER_BUDGET_CEILING_USD", "10")
    ledger = tmp_path / "spend_ledger.json"
    ledger.write_text(
        json.dumps(
            {
                "version": 1,
                "cumulative_spend_usd": "3.42",
                "request_count": 12,
                "paid_call_count": 2,
                "recent_calls": [
                    {
                        "timestamp": "2026-08-31T10:00:00+00:00",
                        "model": "qwen/qwen3-32b:free",
                        "model_role": "role_fast",
                        "latency_s": 0.8,
                        "token_usage": {"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60},
                        "cost_usd": "0.003",
                        "paid": True,
                        "tier": "PAID",
                        "api_key": "sk-should-never-leak",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    client = _app(repo, ledger_path=ledger)
    response = client.get("/router/status")
    assert response.status_code == 200
    body = response.json()
    dumped = json.dumps(body)
    assert "sk-should-never-leak" not in dumped
    assert "OPENROUTER_API_KEY" not in dumped
    assert body["budget"]["spent"] == 3.42
    assert body["budget"]["budget_limit"] == 10.0
    assert body["budget"]["remaining"] == 6.58
    assert body["recent_calls"][0]["model_role"] == "FAST MODEL"
    assert body["recent_calls"][0]["agent_role"] == "intake_agent"


def test_dashboard_rejects_writes():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    client = _app(repo)
    for method in ("post", "put", "patch", "delete"):
        response = getattr(client, method)("/incidents")
        assert response.status_code == 405
        assert response.json()["detail"] == "dashboard is read-only"


def test_qr_tagged_source_and_top_locations():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    tagged = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000020",
            hazard_category="chemical",
            hazard_description="Chemical smell detected",
            location="Chemical Storage",
            status="OPEN",
            current_risk_level="High",
            original_message_text="[LOC:Chemical Storage|Storage Cabinet A] Chemical smell detected",
        )
    )
    for index in range(3):
        repo.create_incident(
            _create_payload(
                incident_ref=f"SL-2026-00002{index + 1}",
                hazard_category="machine",
                hazard_description="Oil leaking near machine",
                location="Lab B",
                status="OPEN",
                current_risk_level="Medium",
                original_message_text="[LOC:Lab B|Machine 4] Oil leaking near machine",
            )
        )
    client = _app(repo)

    listed = client.get("/incidents", params={"status": "OPEN"})
    assert listed.status_code == 200
    qr_row = next(row for row in listed.json()["items"] if row["incident_id"] == "SL-2026-000020")
    assert qr_row["source"] == "QR_TAGGED"
    assert qr_row["location_verified"] is True
    assert qr_row["qr_equipment"] == "Storage Cabinet A"

    detail = client.get(f"/incidents/{tagged.incident_ref}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["source"] == "QR_TAGGED"
    assert payload["location_verified"] is True
    assert payload["qr_equipment"] == "Storage Cabinet A"
    assert payload["location_confidence"] == 1.0
    assert payload["location"] == "Chemical Storage"

    summary = client.get("/analytics/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["qr_tagged_incidents"] == 4
    machine = next(row for row in data["top_qr_locations"] if row["equipment"] == "Machine 4")
    assert machine["location"] == "Lab B"
    assert machine["count"] == 3
    assert machine["insight"]
    assert "Machine 4" in machine["insight"]
    assert "oil" in machine["insight"].lower() or "machine" in machine["insight"].lower()
