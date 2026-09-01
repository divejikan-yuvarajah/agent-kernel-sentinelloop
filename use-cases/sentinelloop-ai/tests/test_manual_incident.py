"""Manual dashboard incidents use the same AI pipeline as Telegram."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from database.repository import IncidentRepository
from services.demo_pipeline import build_demo_orchestrator
from services.incident_intake_service import (
    compose_manual_report_text,
    process_incident_input,
    validate_manual_incident,
)
from tests.test_database import FakeBackend


def _client(repo: IncidentRepository, orch=None) -> TestClient:
    handler = DashboardHandler(repository=repo, orchestrator=orch)
    app = FastAPI()
    app.include_router(handler.get_router())
    return TestClient(app)


def test_validate_manual_incident_requires_location():
    error = validate_manual_incident(
        description="Smoke near the welder",
        category="Fire/Smoke",
        location="",
        people_exposed=2,
    )
    assert error == "Location is required before creating incident"


def test_validate_manual_incident_rejects_bad_image():
    error = validate_manual_incident(
        description="Smoke near the welder",
        category="Fire/Smoke",
        location="CNC Area",
        people_exposed=2,
        photo_filename="notes.pdf",
        photo_content_type="application/pdf",
    )
    assert error == "Image must be jpg, png, or webp"


def test_manual_form_runs_full_pipeline_and_stores_channel():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    orch = build_demo_orchestrator(
        repository=repo,
        raw_text="Smoke detected near welding machine",
        category="fire/smoke",
        location="Welding Section",
        people_exposed=2,
        is_active=True,
        already_injured=False,
    )
    client = _client(repo, orch)
    response = client.post(
        "/api/incidents/manual",
        json={
            "description": "Smoke detected near welding machine",
            "category": "Fire/Smoke",
            "location": "Welding Section",
            "people_exposed": 2,
            "is_active": True,
            "injury_reported": False,
            "created_by": "officer_1",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["incident_id"]
    assert body["input_channel"] == "manual"
    assert body["input_method"] == "dashboard"
    assert body["slack_alert_sent"] is True
    assert body["risk_level"]
    assert body["risk_score"] is not None
    assert "intake_agent" in body["pipeline"]
    assert "risk_agent" in body["pipeline"]
    assert "guidance_agent" in body["pipeline"]
    assert "coordination_agent" in body["pipeline"]
    stored = repo.get_incident_by_ref(body["incident_id"])
    assert stored is not None
    assert stored.source_channel == "manual"
    assert stored.input_method == "dashboard"
    assert stored.created_by == "officer_1"
    assert orch._coord.calls


def test_manual_missing_location_is_400():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    client = _client(repo, build_demo_orchestrator(repository=repo))
    response = client.post(
        "/api/incidents/manual",
        json={
            "description": "Smoke",
            "category": "Fire/Smoke",
            "location": "",
            "people_exposed": 1,
        },
    )
    assert response.status_code == 400
    assert "Location is required" in response.json()["detail"]


def test_process_incident_input_manual_does_not_use_telegram_channel():
    orch = build_demo_orchestrator()
    text = compose_manual_report_text(
        "Oil on the floor at loading bay",
        category="Slip/Trip",
        location="Loading Bay",
        people_exposed=1,
        is_active=True,
        injury_reported=False,
    )
    import asyncio

    result = asyncio.run(
        process_incident_input(
            source="manual",
            raw_text=text,
            metadata={
                "created_by": "officer_2",
                "category": "Slip/Trip",
                "location": "Loading Bay",
                "people_exposed": 1,
                "is_active": True,
                "injury_reported": False,
            },
            orchestrator=orch,
        )
    )
    assert result.error is None
    assert orch._repo.create_calls[0].source_channel == "manual"
    assert orch._repo.create_calls[0].input_method == "dashboard"
    assert orch.telegram.calls == [] or all(call[0] != "forbidden" for call in orch.telegram.calls)
