"""Incident + audit integration for vision suggestions. No live models or storage."""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.incident_agent import analyze_incident, detect_explicit_text_category
from dashboard.api import DashboardHandler
from database.repository import IncidentRepository
from database.schemas import IncidentUpdateCreate
from tests.test_database import FakeBackend, _create_payload
from tools.model_router import ModelCallResult
from tools.vision_tools import vision_override_record

IMAGE_URL = "https://cdn.example.com/workshop/panel.jpg"


def run(coro):
    return asyncio.run(coro)


class DualRouter:
    def __init__(self, *, fast: dict | None = None, vision: dict | None = None) -> None:
        self.fast = fast
        self.vision = vision
        self.calls: list[str] = []

    async def __call__(self, role: str = "", messages: list | None = None, **kwargs):
        self.calls.append(role)
        if role == "role_vision":
            return ModelCallResult(
                content=json.dumps(self.vision or {}),
                model="mock/vision",
                role="role_vision",
                paid=False,
            )
        payload = {
            "hazard_category": None,
            "location": None,
            "equipment_involved": None,
            "people_exposed": None,
            "is_active": True,
            "already_injured": False,
            "secondary_hazards": [],
            "emergency_type": None,
            "emergency_reason": None,
            "emergency_confidence": 0.0,
            "risk_indicators": [],
            "injury_summary": None,
            "exposure_type": None,
            "equipment_state": None,
            "worker_reports_urgent": False,
            "severity": "medium",
            "classification_reason": "Supported by the worker report.",
            "confidence": {
                "hazard_category": 0.2,
                "location": 0.2,
                "equipment_involved": 0.2,
                "people_exposed": 0.1,
                "is_active": 0.8,
                "already_injured": 0.9,
            },
            "evidence": {},
        }
        if self.fast:
            extra = dict(self.fast)
            conf_update = extra.pop("confidence", None)
            payload.update(extra)
            if isinstance(conf_update, dict):
                merged = dict(payload["confidence"])
                merged.update(conf_update)
                payload["confidence"] = merged
        return ModelCallResult(content=json.dumps(payload), model="mock/fast", role="role_fast", paid=False)


def _app(repo: IncidentRepository) -> TestClient:
    handler = DashboardHandler(repository=repo)
    app = FastAPI()
    app.include_router(handler.get_router())
    return TestClient(app)


def test_image_missing_category_fills_from_vision():
    router = DualRouter(
        vision={
            "hazard_category": "electrical",
            "confidence": 0.88,
            "observations": ["damaged electrical panel", "exposed terminals"],
        }
    )
    result = run(
        analyze_incident(
            {
                "has_image": True,
                "image_url": IMAGE_URL,
                "image_mime_type": "image/jpeg",
            },
            call_model_fn=router,
        )
    )
    assert "role_vision" in router.calls
    assert "role_fast" not in router.calls
    assert result.hazard_category == "electrical"
    assert result.category_source == "vision_suggestion"
    assert result.vision_hazard_category == "electrical"
    assert result.vision_confidence == 0.88
    assert result.vision_observations


def test_explicit_worker_text_wins_over_vision():
    router = DualRouter(
        fast={
            "hazard_category": "chemical",
            "confidence": {"hazard_category": 0.4},
        },
        vision={
            "hazard_category": "chemical",
            "confidence": 0.91,
            "observations": ["liquid spill visible"],
        },
    )
    text = "Electrical cable broken"
    assert detect_explicit_text_category(text) == "electrical"
    result = run(
        analyze_incident(
            {
                "translated_text": text,
                "has_image": True,
                "image_url": IMAGE_URL,
                "image_mime_type": "image/jpeg",
            },
            call_model_fn=router,
        )
    )
    assert result.hazard_category == "electrical"
    assert result.category_source == "worker_text"
    assert "role_vision" not in router.calls
    assert result.vision_hazard_category is None


def test_high_confidence_extracted_category_skips_vision():
    router = DualRouter(
        fast={
            "hazard_category": "machine",
            "confidence": {"hazard_category": 0.94},
        },
        vision={
            "hazard_category": "chemical",
            "confidence": 0.9,
            "observations": ["container"],
        },
    )
    result = run(
        analyze_incident(
            {
                "translated_text": "The rotating mill is unguarded",
                "has_image": True,
                "image_url": IMAGE_URL,
            },
            call_model_fn=router,
        )
    )
    assert result.hazard_category == "machine"
    assert "role_vision" not in router.calls


def test_human_override_is_stored_on_audit_export():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    incident = repo.create_incident(
        _create_payload(
            incident_ref="SL-2026-000421",
            hazard_category="electrical",
            location="CNC Area",
        )
    )
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=incident.id,
            update_type="vision_suggestion",
            actor_type="agent",
            actor_reference="incident_agent",
            message="AI Vision Suggestion",
            metadata={
                "vision_hazard_category": "chemical",
                "vision_confidence": 0.71,
                "vision_observations": ["liquid spill visible", "chemical container nearby"],
                "vision_model_used": "mock/vision",
                "final_category": "electrical",
                "suggestion_only": True,
            },
        )
    )
    repo.add_update(
        IncidentUpdateCreate(
            incident_id=incident.id,
            update_type="vision_override",
            actor_type="safety_officer",
            actor_reference="N. Fernando",
            message="Human changed vision suggestion",
            metadata=vision_override_record(
                vision_category="chemical",
                final_category="electrical",
                reason="Worker text and panel inspection confirmed electrical",
                changed_by="N. Fernando",
            ),
        )
    )
    client = _app(repo)
    audit = client.get(f"/api/incidents/{incident.incident_ref}/audit-export")
    assert audit.status_code == 200
    body = audit.json()
    suggestion = body["vision_suggestion"]
    assert suggestion["category"] == "chemical"
    assert suggestion["confidence"] == 0.71
    assert suggestion["final_decision"] == "electrical"
    assert suggestion["override"] is True
    assert suggestion["changed_by"] == "N. Fernando"
    assert suggestion["override_reason"]
    dumped = json.dumps(body)
    assert "sk-" not in dumped.lower() or "sk-should" not in dumped

    detail = client.get(f"/api/incidents/{incident.incident_ref}")
    assert detail.status_code == 200
    vision = detail.json()["vision"]
    assert vision["vision_override"] is True
    assert vision["final_category"] == "electrical"
    assert vision["hazard_category"] == "chemical"
    titles = [event["title"] for event in detail.json()["timeline"]]
    assert any("Vision AI analyzed image" in title for title in titles)
    assert any("Suggested chemical hazard" in title for title in titles)
