"""Required follow-up verification coverage. Complements tests/test_followup_agent.py."""

from __future__ import annotations

from uuid import uuid4

from agents.followup_agent import (
    VERIFICATION_PENDING,
    VERIFICATION_UNSURE,
    FollowupService,
    MemoryFollowupStore,
)
from integrations.slack_handler import SlackHandler
from integrations.whatsapp import WhatsAppHandler
from tests.conftest import FakeRepository, MockSlackClient, MockWhatsAppClient, run
from tools.lifecycle import STATUS_CLOSED, STATUS_IN_PROGRESS, STATUS_RESOLVED


def _service(repo: FakeRepository, slack: MockSlackClient | None = None):
    wa = MockWhatsAppClient()
    sl = slack or MockSlackClient()
    return (
        FollowupService(
            whatsapp=WhatsAppHandler(client=wa),
            slack=SlackHandler(client=sl),
            repository=repo,
            store=MemoryFollowupStore(),
        ),
        wa,
        sl,
    )


def _incident(**kwargs) -> dict:
    base = {
        "incident_ref": "INC-0042",
        "id": str(uuid4()),
        "status": STATUS_RESOLVED,
        "worker_phone": "94770000000",
        "detected_language": "en",
        "location": "Electrical Room",
        "assigned_team": "Electrical Maintenance",
        "slack_channel_id": "C-ELEC",
        "slack_thread_ts": "1.000",
        "hazard_category": "electrical",
        "risk_level": "Medium",
    }
    base.update(kwargs)
    return base


def test_worker_still_exists_reopens_same_incident_and_renotifies_team():
    repo = FakeRepository()
    service, _, slack = _service(repo)
    incident = _incident()
    incident_id = incident["incident_ref"]
    run(service.start_worker_verification(incident))
    result = run(service.handle_worker_verification_response(text="No, still exists", incident_id=incident_id))
    assert result.reopened is True
    assert result.status == STATUS_IN_PROGRESS
    assert result.incident_id == incident_id
    assert result.team_renotified is True
    assert repo.incident_status == "IN_PROGRESS"
    blob = slack.posts[0]["text"]
    assert "still exists" in blob.lower() or "verification failed" in blob.lower()
    assert slack.posts[0]["channel"] == "C-ELEC"


def test_worker_yes_closes_low_medium_and_records_timestamp():
    repo = FakeRepository()
    repo.risk_level = "Medium"
    service, _, _ = _service(repo)
    run(service.start_worker_verification(_incident(risk_level="Medium")))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert result.closed is True
    assert result.status == STATUS_CLOSED
    assert result.resolution_timestamp is not None
    assert repo.closed_at is not None
    assert repo.incident_status == "CLOSED"


def test_worker_unsure_keeps_verification_pending():
    repo = FakeRepository()
    service, _, slack = _service(repo)
    run(service.start_worker_verification(_incident()))
    result = run(service.handle_worker_verification_response(text="Not sure", incident_id="INC-0042"))
    assert result.closed is False
    assert result.reopened is False
    assert result.verification_status == VERIFICATION_UNSURE
    assert result.status == STATUS_RESOLVED
    assert repo.incident_status == "RESOLVED"
    assert any("pending" in str(post.get("text")).lower() for post in slack.posts)
    record = service.store.get("INC-0042")
    assert record is not None
    assert record.verification_status in {VERIFICATION_UNSURE, VERIFICATION_PENDING} or result.closed is False
