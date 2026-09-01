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

    open_rows = client.get("/api/incidents", params={"status": "OPEN"})
    assert open_rows.status_code == 200
    body = open_rows.json()
    assert body["total"] == 1
    assert body["items"][0]["incident_id"] == "SL-2026-000010"
    assert body["items"][0]["risk_level"] == "CRITICAL"
    assert "evidence" not in body["items"][0]
    assert body["items"][0]["assigned_officer"]

    critical = client.get("/api/incidents", params={"risk_level": "CRITICAL"})
    assert critical.status_code == 200
    assert critical.json()["total"] == 1

    page = client.get("/api/incidents", params={"limit": 2, "offset": 0, "sort_by": "newest"})
    assert page.status_code == 200
    assert page.json()["limit"] == 2
    assert len(page.json()["items"]) == 2

    oldest = client.get("/api/incidents", params={"sort_by": "oldest"})
    ids = [row["incident_id"] for row in oldest.json()["items"]]
    assert ids[0] == "SL-2026-000012"

    riskiest = client.get("/api/incidents", params={"sort_by": "highest_risk"})
    assert riskiest.json()["items"][0]["risk_level"] == "CRITICAL"


def test_incident_detail_and_404():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    seeded = _seed(repo, backend)
    client = _app(repo)

    missing = client.get("/api/incidents/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "incident not found"

    found = client.get("/api/incidents/SL-2026-000010")
    assert found.status_code == 200
    payload = found.json()
    assert payload["incident_id"] == "SL-2026-000010"
    assert payload["risk"]["risk_level"] == "CRITICAL"
    assert payload["risk"]["risk_score"] == 20
    assert payload["duplicates"]["duplicate_count"] == 3
    assert payload["timeline"]
    assert "••••" in payload["reporter"]["reporter_id"]
    assert "+94771234567" not in json.dumps(payload)
    by_uuid = client.get(f"/api/incidents/{seeded['chemical'].id}")
    assert by_uuid.status_code == 200
    assert by_uuid.json()["incident_id"] == "SL-2026-000010"


def test_analytics_and_recurring():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    _seed(repo, backend)
    client = _app(repo)

    summary = client.get("/api/analytics/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["total_incidents"] == 4
    assert data["open_incidents"] == 3
    assert data["critical_incidents"] == 1
    assert data["resolved_today"] == 1
    assert data["incidents_by_risk_level"]["CRITICAL"] == 1
    assert "Chemical Leak" in data["incidents_by_category"]
    assert len(data["loop_stages"]) == 7

    recurring = client.get("/api/analytics/recurring")
    assert recurring.status_code == 200
    items = recurring.json()["items"]
    assert items
    chemical = next(row for row in items if row["category"] == "Chemical Leak")
    assert chemical["count"] == 3
    assert chemical["location"] == "Factory Area A"
    assert chemical["period"] == "30 days"
    assert chemical["recommendation"]


def test_live_feed_decodes_json_envelopes():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    created = repo.create_incident(_create_payload(incident_ref="DEMO-HORIZON-009", status="ASSESSING"))
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=created.id,
            update_type="timeline",
            message=json.dumps(
                {
                    "demo_key": "demo_horizon_incident_009:wa_0",
                    "update_type": "telegram_inbound",
                    "message": "Crack appearing in the loading-bay beam",
                    "actor_type": "worker",
                    "metadata": {"channel": "telegram"},
                }
            ),
        )
    )
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=created.id,
            update_type="timeline",
            message=json.dumps(
                {
                    "demo_key": "demo_horizon_incident_009:lifecycle_0",
                    "update_type": "status_transition",
                    "message": "New → Validating",
                    "previous_status": "REPORTED",
                    "new_status": "ASSESSING",
                }
            ),
        )
    )
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=created.id,
            update_type="timeline",
            message=json.dumps(
                {
                    "update_type": "guidance_fallback",
                    "message": "Invented instruction blocked; knowledge-base line released instead.",
                    "metadata": {"hallucination_check": "Blocked"},
                }
            ),
        )
    )
    client = _app(repo)
    data = client.get("/api/analytics/summary").json()
    events = data["recent_activity"]
    assert events
    assert not any(str(item["summary"]).lstrip().startswith("{") for item in events)
    kinds = {item["kind"] for item in events}
    summaries = {item["summary"] for item in events}
    assert "Worker report" in kinds
    assert "Guardrail blocked" in kinds
    assert "Status" in kinds
    assert "Crack appearing in the loading-bay beam" in summaries
    assert "Invented instruction blocked; knowledge-base line released instead." in summaries


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
    response = client.get("/api/router/status")
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
        response = getattr(client, method)("/api/incidents")
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

    listed = client.get("/api/incidents", params={"status": "OPEN"})
    assert listed.status_code == 200
    qr_row = next(row for row in listed.json()["items"] if row["incident_id"] == "SL-2026-000020")
    assert qr_row["source"] == "QR_TAGGED"
    assert qr_row["location_verified"] is True
    assert qr_row["qr_equipment"] == "Storage Cabinet A"

    detail = client.get(f"/api/incidents/{tagged.incident_ref}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["source"] == "QR_TAGGED"
    assert payload["location_verified"] is True
    assert payload["qr_equipment"] == "Storage Cabinet A"
    assert payload["location_confidence"] == 1.0
    assert payload["location"] == "Chemical Storage"

    summary = client.get("/api/analytics/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["qr_tagged_incidents"] == 4
    machine = next(row for row in data["top_qr_locations"] if row["equipment"] == "Machine 4")
    assert machine["location"] == "Lab B"
    assert machine["count"] == 3
    assert machine["insight"]
    assert "Machine 4" in machine["insight"]
    assert "oil" in machine["insight"].lower() or "machine" in machine["insight"].lower()


def test_repeated_hazard_widgets():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    created = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000030",
            hazard_category="machine",
            hazard_description="Oil leaking from hydraulic machine",
            location="Production Floor",
            status="OPEN",
            current_risk_level="Medium",
        )
    )
    for row in backend.tables["incidents"]:
        if row["incident_ref"] == created.incident_ref:
            row["duplicate_count"] = 12
    client = _app(repo)
    summary = client.get("/api/analytics/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["most_repeated_hazards"]
    top = data["most_repeated_hazards"][0]
    assert top["count"] == 12
    assert "Production Floor" in top["label"]
    assert top["insight"]
    assert data["repeated_hazard_locations"][0]["location"] == "Production Floor"
    listed = client.get("/api/incidents")
    card = next(row for row in listed.json()["items"] if row["incident_id"] == "SL-2026-000030")
    assert card["duplicate_count"] == 12


def _prediction_seed(repo: IncidentRepository, backend: FakeBackend) -> None:
    now = datetime.now(timezone.utc)
    specs = [
        ("SL-2026-P01", "electrical", "CNC Area", 8),
        ("SL-2026-P02", "electrical", "CNC Area", 3),
        ("SL-2026-P03", "electrical", "CNC Area", 1),
        ("SL-2026-P04", "electrical", "CNC Area", 0),
        ("SL-2026-P05", "chemical", "Chemical Storage Room", 6),
        ("SL-2026-P06", "chemical", "Chemical Storage Room", 2),
        ("SL-2026-P07", "chemical", "Chemical Storage Room", 0),
        ("SL-2026-P08", "slip/trip", "Loading Bay", 12),
        ("SL-2026-P09", "slip/trip", "Loading Bay", 4),
    ]
    for ref, category, location, days_ago in specs:
        repo.create_incident(
            _create_payload(
                incident_ref=ref,
                hazard_category=category,
                location=location,
                status="OPEN",
                current_risk_level="High",
            )
        )
        for row in backend.tables["incidents"]:
            if row["incident_ref"] == ref:
                row["created_at"] = (now - timedelta(days=days_ago)).isoformat()


class _PredictionRouter:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, role: str = "", messages: list | None = None, **kwargs):
        self.calls += 1
        assert role == "role_reasoning"
        location = "site"
        if messages:
            try:
                payload = json.loads(messages[-1]["content"])
                location = payload.get("location") or location
            except (TypeError, json.JSONDecodeError, KeyError):
                pass
        from tools.model_router import ModelCallResult

        return ModelCallResult(
            content=json.dumps(
                {
                    "recommendation": f"Inspect {location} before next shift",
                    "reason": "related incidents detected",
                    "confidence": 0.9,
                }
            ),
            model="mock",
            role="role_reasoning",
            paid=False,
        )


def test_analytics_predictions_format_cache_and_empty_state():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    router = _PredictionRouter()
    handler = DashboardHandler(repository=repo, call_model_fn=router)
    app = FastAPI()
    app.include_router(handler.get_router())
    client = TestClient(app)

    empty = client.get("/api/analytics/predictions")
    assert empty.status_code == 200
    body = empty.json()
    assert body["prediction_count"] == 0
    assert body["predictions"] == []
    assert "generated_at" in body
    assert "last_updated" in body
    assert router.calls == 0

    _prediction_seed(repo, backend)
    handler._cache.clear()
    first = client.get("/api/analytics/predictions")
    assert first.status_code == 200
    data = first.json()
    assert data["prediction_count"] >= 2
    assert {row["location"] for row in data["predictions"]} >= {"CNC Area", "Chemical Storage Room"}
    for row in data["predictions"]:
        assert "recommendation" in row
        assert "trend" in row
        assert "reason" in row
    calls_after_first = router.calls
    assert calls_after_first == data["prediction_count"]

    second = client.get("/api/analytics/predictions")
    assert second.status_code == 200
    assert router.calls == calls_after_first
    assert second.json()["prediction_count"] == data["prediction_count"]

    forbidden = client.post("/api/analytics/predictions", json={})
    assert forbidden.status_code == 405


class _FakeInspectionService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def request_inspection(self, payload: dict) -> object:
        from agents.coordination_agent import CoordinationResult

        self.calls.append(payload)
        return CoordinationResult(
            posted=True,
            message_type="inspection_request",
            location=str(payload.get("location") or ""),
            slack_channel_id="C-LAB",
        )


def test_analytics_predictions_inspect_posts_slack_note():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    coord = _FakeInspectionService()
    handler = DashboardHandler(repository=repo, coordination_service=coord)
    app = FastAPI()
    app.include_router(handler.get_router())
    client = TestClient(app)

    response = client.post(
        "/api/analytics/predictions/inspect",
        json={
            "location": "CNC Area",
            "category": "electrical",
            "reason": "Recurring electrical incidents detected.",
            "recommendation": "Inspect electrical panel before next shift.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["posted"] is True
    assert body["message_type"] == "inspection_request"
    assert body["location"] == "CNC Area"
    assert body["slack_channel_id"] == "C-LAB"
    assert len(coord.calls) == 1
    assert coord.calls[0]["location"] == "CNC Area"
