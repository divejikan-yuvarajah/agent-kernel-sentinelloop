"""Live dashboard reads pick up newly created incidents without a page reload."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from database.repository import IncidentRepository
from services.demo_pipeline import build_demo_orchestrator
from tests.test_database import FakeBackend


def test_incident_list_updates_after_manual_create():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    orch = build_demo_orchestrator(repository=repo, location="Electrical Room")
    app = FastAPI()
    app.include_router(DashboardHandler(repository=repo, orchestrator=orch).get_router())
    client = TestClient(app)

    before = client.get("/api/incidents")
    assert before.status_code == 200
    prior = {row["incident_id"] for row in before.json()["items"]}

    created = client.post(
        "/api/incidents/manual",
        json={
            "description": "Electrical failure at the isolator",
            "category": "Electrical",
            "location": "Electrical Room",
            "people_exposed": 3,
            "is_active": True,
            "injury_reported": False,
        },
    )
    assert created.status_code == 200, created.text
    incident_id = created.json()["incident_id"]
    assert incident_id

    after = client.get("/api/incidents")
    assert after.status_code == 200
    ids = {row["incident_id"] for row in after.json()["items"]}
    assert incident_id in ids
    assert incident_id not in prior
    match = next(row for row in after.json()["items"] if row["incident_id"] == incident_id)
    assert match["status"]
    assert match["input_channel"] in {"manual", "dashboard"}
