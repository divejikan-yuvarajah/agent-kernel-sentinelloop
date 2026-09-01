"""Shift handover agent tests. No live Slack, OpenRouter, or Supabase."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.handover_agent import (
    collect_handover_snapshot,
    generate_handover_summary,
    handover_analytics,
    load_handover_config,
)
from dashboard.api import DashboardHandler
from database.repository import IncidentRepository
from integrations.slack_handler import SlackHandler, handover_fallback_text
from tests.conftest import FakeRepository, MockModelRouter, MockSlackClient, run
from tests.test_database import FakeBackend, _create_payload

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 1, 22, 1, tzinfo=timezone.utc)


def _row(**overrides) -> dict:
    data = {
        "id": uuid4(),
        "incident_ref": "INC-00421",
        "hazard_category": "Electrical",
        "location": "CNC Area",
        "current_risk_level": "Critical",
        "status": "IN_PROGRESS",
        "created_at": NOW - timedelta(hours=2),
        "updated_at": NOW - timedelta(hours=1),
        "reviewed_by_human": False,
    }
    data.update(overrides)
    return data


def test_new_incident_detection():
    repo = FakeRepository(
        [
            _row(incident_ref="INC-NEW", created_at=NOW - timedelta(hours=1)),
            _row(incident_ref="INC-OLD", created_at=NOW - timedelta(days=2), status="CLOSED", current_risk_level="Low"),
        ]
    )
    snapshot = collect_handover_snapshot(
        repo.list_incidents(),
        shift_label="Evening Shift",
        now=NOW,
        previous_generated_at=NOW - timedelta(hours=8),
    )
    ids = {item["incident_id"] for item in snapshot["new_incident_rows"]}
    assert "INC-NEW" in ids
    assert "INC-OLD" not in ids
    assert snapshot["new_incidents"] == 1


def test_critical_review_detection():
    snapshot = collect_handover_snapshot(
        [
            _row(incident_ref="INC-CRIT", current_risk_level="Critical", reviewed_by_human=False),
            _row(incident_ref="INC-HIGH", current_risk_level="High", reviewed_by_human=False, status="OPEN"),
            _row(incident_ref="INC-OK", current_risk_level="Critical", reviewed_by_human=True),
            _row(incident_ref="INC-LOW", current_risk_level="Low", status="OPEN"),
        ],
        shift_label="Evening Shift",
        now=NOW,
        previous_generated_at=NOW - timedelta(hours=8),
    )
    review_ids = {item["incident_id"] for item in snapshot["review_rows"]}
    assert "INC-CRIT" in review_ids
    assert "INC-HIGH" in review_ids
    assert "INC-OK" not in review_ids
    assert snapshot["human_review_required"] == 2
    assert snapshot["critical_open_incidents"] >= 1


def test_awaiting_verification_timeout():
    snapshot = collect_handover_snapshot(
        [
            _row(
                incident_ref="INC-LATE",
                status="AWAITING_VERIFICATION",
                current_risk_level="Medium",
                created_at=NOW - timedelta(hours=30),
                updated_at=NOW - timedelta(hours=30),
            ),
            _row(
                incident_ref="INC-FRESH",
                status="AWAITING_VERIFICATION",
                current_risk_level="Medium",
                created_at=NOW - timedelta(hours=2),
                updated_at=NOW - timedelta(hours=2),
            ),
        ],
        shift_label="Evening Shift",
        now=NOW,
        verification_timeout_hours=24,
    )
    overdue_ids = {item["incident_id"] for item in snapshot["overdue_rows"]}
    assert "INC-LATE" in overdue_ids
    assert "INC-FRESH" not in overdue_ids
    assert snapshot["awaiting_verification_overdue"] == 1


def test_role_fast_called_once():
    repo = FakeRepository([_row()])
    router = MockModelRouter()
    router.set_json({"summary_text": "Evening Shift Safety Handover\n• 1 new incidents reported"})
    record = run(
        generate_handover_summary(
            "Evening Shift",
            repository=repo,
            call_model_fn=router,
            slack=None,
            now=NOW,
        )
    )
    assert len(router.calls) == 1
    assert router.calls[0][0] == "role_fast"
    assert record["shift_label"] == "Evening Shift"
    assert "handover_id" in record
    assert "summary_text" in record
    assert record["open_incident_count"] >= 1


def test_slack_summary_posted():
    repo = FakeRepository([_row()])
    router = MockModelRouter()
    router.set_json({"summary_text": "Evening Shift Safety Handover\n• 1 Critical incident still open"})
    client = MockSlackClient()
    slack = SlackHandler(client=client, destinations={"Safety Supervisor": "C-SAFETY"})
    record = run(
        generate_handover_summary(
            "Evening Shift",
            repository=repo,
            call_model_fn=router,
            slack=slack,
            now=NOW,
        )
    )
    assert client.posts
    posted = client.posts[0]
    assert posted["channel"] == "C-SAFETY"
    blob = str(posted.get("text") or "") + str(posted.get("blocks") or "")
    assert "Evening Shift" in blob
    assert "Critical" in blob or str(record["critical_open_count"]) in blob
    fallback = handover_fallback_text(record=record, snapshot=record.get("structured") or {})
    assert "Evening Shift" in fallback
    assert record["slack_posted"] is True


def test_handover_generate_api():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    repo.create_incident(
        _create_payload(
            incident_ref="INC-00421",
            hazard_category="Electrical",
            location="CNC Area",
            status="IN_PROGRESS",
            current_risk_level="Critical",
        )
    )
    router = MockModelRouter()
    router.set_json({"summary_text": "Evening Shift Safety Handover\n• 1 Critical incident still open"})
    handler = DashboardHandler(repository=repo, call_model_fn=router)
    handler._slack = SlackHandler(client=MockSlackClient(), destinations={"Safety Supervisor": "C-SAFETY"})
    app = FastAPI()
    app.include_router(handler.get_router())
    client = TestClient(app)
    response = client.post("/api/handover/generate", json={"shift_label": "Evening Shift"})
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "summary_text" in body["handover"]
    assert "critical_open_count" in body["handover"]
    assert body["handover"]["shift_label"] == "Evening Shift"


def test_scheduler_phase_two_documented_when_kernel_has_no_cron():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Phase 2:" in readme
    assert "Automatic shift-end scheduling using Agent Kernel scheduler." in readme
    config = load_handover_config()
    assert config["morning_shift_end"] == "14:00"
    assert config["evening_shift_end"] == "22:00"
    assert config["verification_timeout_hours"] == 24


def test_handover_repository_round_trip():
    backend = FakeBackend()
    repo = IncidentRepository(backend, storage_bucket="evidence")
    created = repo.create_handover_summary(
        {
            "handover_id": str(uuid4()),
            "shift_label": "Morning Shift",
            "summary_text": "Morning briefing",
            "open_incident_count": 5,
            "critical_open_count": 2,
            "generated_by": "handover_agent",
            "payload": {
                "top_risks": [{"location": "Chemical Storage", "category": "Chemical Leak", "risk": "Critical"}]
            },
        }
    )
    latest = repo.get_latest_handover()
    assert latest is not None
    assert latest.shift_label == "Morning Shift"
    assert latest.critical_open_count == 2
    assert created.summary_text == "Morning briefing"
    analytics = handover_analytics(repo)
    assert analytics["total_handovers"] == 1
    assert analytics["compare"]["morning"]["critical"] == 2


def test_model_is_not_called_twice_when_slack_fails():
    repo = FakeRepository([_row()])
    router = MockModelRouter()
    router.set_json({"summary_text": "Evening Shift Safety Handover"})
    client = MockSlackClient()
    client.fail = True
    slack = SlackHandler(client=client, destinations={"Safety Supervisor": "C-SAFETY"})
    record = run(
        generate_handover_summary("Evening Shift", repository=repo, call_model_fn=router, slack=slack, now=NOW)
    )
    assert len(router.calls) == 1
    assert record["handover_id"]
    assert record["slack_posted"] is False
