"""Command-center system health endpoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.api import DashboardHandler
from database.repository import IncidentRepository
from tests.test_database import FakeBackend, _create_payload


def test_system_health_shape():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    repo.create_incident(_create_payload(incident_ref="SL-2026-HEALTH"))
    app = FastAPI()
    app.include_router(DashboardHandler(repository=repo).get_router())
    client = TestClient(app)

    response = client.get("/api/system-health")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("telegram", "slack", "database", "ai_services", "last_incident"):
        assert key in body
    assert body["database"] == "connected"
    assert body["last_incident_label"]
    assert body["telegram"] in {"connected", "disconnected", "warning"}
    assert body["slack"] in {"connected", "disconnected", "warning"}
    assert body["ai_services"] in {"available", "unavailable", "warning"}
