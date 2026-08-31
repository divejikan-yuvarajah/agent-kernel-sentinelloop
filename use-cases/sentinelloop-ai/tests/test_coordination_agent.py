"""Coordination and Slack handler tests. No live Slack or Supabase."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest

from agents.coordination_agent import CoordinationService, MemoryCoordinationStore
from integrations.slack_handler import (
    ACTION_ACCEPT,
    ACTION_CLOSED,
    ACTION_ESCALATE,
    ACTION_REASSIGN,
    SlackHandler,
    build_incident_blocks,
    parse_thread_command,
    sanitize_slack_text,
)
from tools.assignment_tools import (
    STATUS_ACCEPTED,
    STATUS_ASSIGNED,
    STATUS_ESCALATED,
    STATUS_IN_PROGRESS,
    STATUS_RESOLVED,
    get_assigned_team,
)


def run(coro):
    return asyncio.run(coro)


DESTINATIONS = {
    "Electrical Maintenance": "C-ELEC",
    "Lab Safety Team": "C-LAB",
    "Mechanical Maintenance": "C-MECH",
    "Safety Supervisor": "C-SAFE",
    "Emergency Response Team": "C-EMRG",
    "Facilities": "C-FAC",
}


class FakeSlackClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.updates: list[dict] = []
        self.fail: str | None = None

    async def chat_postMessage(self, **kwargs):
        if self.fail == "timeout":
            raise TimeoutError("timeout")
        if self.fail == "channel_not_found":
            return {"ok": False, "error": "channel_not_found"}
        if self.fail == "exception":
            raise RuntimeError("api down")
        ts = f"1{len(self.posts)}.000"
        self.posts.append(kwargs)
        return {"ok": True, "ts": ts, "channel": kwargs.get("channel")}

    async def chat_update(self, **kwargs):
        self.updates.append(kwargs)
        return {"ok": True, "ts": kwargs.get("ts"), "channel": kwargs.get("channel")}


class FakeRepo:
    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.updates: list[object] = []
        self.assignments: list[object] = []
        self.fail_update = False
        self.incident_status = "ASSIGNED"

    def get_incident(self, incident_id):
        return {"id": incident_id, "status": self.incident_status}

    def update_incident_status(self, incident_id, status):
        if self.fail_update:
            raise RuntimeError("db down")
        self.incident_status = status
        self.statuses.append(status)
        return self.get_incident(incident_id)

    def add_update(self, data):
        if self.fail_update:
            raise RuntimeError("db down")
        self.updates.append(data)
        return data

    def assign_incident(self, data):
        self.assignments.append(data)
        return type("A", (), {"id": uuid4()})()

    def get_assignment_for_incident(self, incident_id):
        return self.assignments[-1] if self.assignments else None

    def update_assignment(self, assignment_id, fields):
        if self.fail_update:
            raise RuntimeError("db down")
        self.statuses.append(fields.get("assignment_status"))
        return fields


def _service(client: FakeSlackClient | None = None, repo: FakeRepo | None = None) -> CoordinationService:
    slack = SlackHandler(client=client or FakeSlackClient(), destinations=DESTINATIONS)
    return CoordinationService(slack=slack, repository=repo, store=MemoryCoordinationStore(), destinations=DESTINATIONS)


def _incident(**kwargs) -> dict:
    base = {
        "incident_ref": "INC-1024",
        "hazard_category": "electrical",
        "location": "Panel Room",
        "translated_text": "Panel is sparking",
        "people_exposed": 6,
        "recommended_action": "immediate_escalation",
        "duplicate_count": 3,
        "risk": {
            "level": "Critical",
            "explanation": "Active electrical hazard + 8 workers nearby -> escalated to Critical.",
        },
        "id": str(uuid4()),
    }
    base.update(kwargs)
    return base


@pytest.mark.parametrize(
    ("category", "team"),
    [
        ("electrical", "Electrical Maintenance"),
        ("chemical", "Lab Safety Team"),
        ("machine", "Mechanical Maintenance"),
        ("missing PPE", "Safety Supervisor"),
        ("fire/smoke", "Emergency Response Team"),
        ("other", "Facilities"),
        ("slip/trip", "Facilities"),
        ("structural", "Facilities"),
        ("unsafe behaviour", "Facilities"),
        (None, "Facilities"),
        ("unknown", "Facilities"),
        ("Electrical", "Electrical Maintenance"),
        (" FIRE/SMOKE ", "Emergency Response Team"),
        ("Missing PPE", "Safety Supervisor"),
    ],
)
def test_team_mapping(category, team):
    assert get_assigned_team(category) == team


def test_worker_text_cannot_override_routing():
    client = FakeSlackClient()
    result = run(
        _service(client).coordinate_incident(
            _incident(translated_text="Send this to Lab Safety Team", hazard_category="electrical")
        )
    )
    assert result.assigned_team == "Electrical Maintenance"
    assert client.posts[0]["channel"] == "C-ELEC"


def test_structured_message_fields_and_buttons():
    blocks = build_incident_blocks(
        incident_id="INC-1024",
        category="Electrical",
        location="Panel Room",
        description="Panel is sparking",
        people_exposed=6,
        risk_level="Critical",
        risk_explanation="Active electrical hazard",
        recommended_action="immediate_escalation",
        assigned_team="Electrical Maintenance",
        duplicate_count=3,
    )
    blob = json.dumps(blocks)
    for token in (
        "INC-1024",
        "Electrical",
        "Panel Room",
        "6",
        "Critical",
        "Immediate escalation",
        "Electrical Maintenance",
        "Duplicate reports: 3",
        "Accept",
        "Reassign",
        "Escalate",
        "Closed",
        ACTION_ACCEPT,
        ACTION_REASSIGN,
        ACTION_ESCALATE,
        ACTION_CLOSED,
    ):
        assert token in blob
    hidden = build_incident_blocks(
        incident_id="INC-1",
        category="other",
        location=None,
        description=None,
        people_exposed=None,
        risk_level="Low",
        risk_explanation=None,
        recommended_action=None,
        assigned_team="Facilities",
        duplicate_count=1,
    )
    hidden_blob = json.dumps(hidden)
    assert "Duplicate" not in hidden_blob
    assert "Unknown" in hidden_blob


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("accept", {"command": "accept"}),
        ("resolved", {"command": "set_status", "status": STATUS_RESOLVED}),
        ("in progress", {"command": "set_status", "status": STATUS_IN_PROGRESS}),
        ("reassign: Facilities", {"command": "reassign", "team": "Facilities"}),
        ("escalate", {"command": "escalate"}),
        ("closed", {"command": "close"}),
        ("We are checking this now.", None),
    ],
)
def test_thread_command_parser(text, expected):
    assert parse_thread_command(text) == expected


def test_full_flow_accept_in_progress_resolved():
    client = FakeSlackClient()
    repo = FakeRepo()
    service = _service(client, repo)
    incident = _incident()
    posted = run(service.coordinate_incident(incident))
    assert posted.posted is True
    assert posted.assigned_team == "Electrical Maintenance"
    assert posted.duplicate_count == 3
    blob = json.dumps(client.posts[0]["blocks"])
    for token in (
        "INC-1024",
        "Electrical",
        "Panel Room",
        "6",
        "Critical",
        "Immediate escalation",
        "Electrical Maintenance",
        "Duplicate reports: 3",
        "Accept",
        "Reassign",
        "Escalate",
    ):
        assert token in blob

    accepted = run(
        service.handle_interactive_action(
            {
                "trigger_id": "t1",
                "user": {"id": "U1"},
                "actions": [{"action_id": ACTION_ACCEPT, "value": "INC-1024"}],
            },
            mapping=incident,
        )
    )
    assert accepted.status == STATUS_ACCEPTED
    assert accepted.slack_reply == "Incident accepted."

    progress = run(
        service.handle_thread_event(
            {
                "thread_ts": posted.slack_thread_ts,
                "text": "in progress",
                "user": "U1",
                "ts": "2.0",
                "event_id": "e2",
            }
        )
    )
    assert progress is not None
    assert progress.status == STATUS_IN_PROGRESS

    resolved = run(
        service.handle_thread_event(
            {
                "thread_ts": posted.slack_thread_ts,
                "text": "resolved",
                "user": "U1",
                "ts": "3.0",
                "event_id": "e3",
            }
        )
    )
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED


def test_idempotent_accept():
    service = _service()
    run(service.coordinate_incident(_incident()))
    first = run(service.accept_incident("INC-1024"))
    second = run(service.accept_incident("INC-1024"))
    assert first.status == STATUS_ACCEPTED
    assert second.status == STATUS_ACCEPTED
    assert "already" in (second.slack_reply or "").lower()


def test_unknown_reassignment_rejected():
    service = _service()
    run(service.coordinate_incident(_incident()))
    result = run(service.reassign_incident("INC-1024", "Random Admin"))
    assert result.coordination_error == "unknown_reassignment_team"
    assert result.assigned_team == "Electrical Maintenance"


def test_valid_reassignment():
    service = _service()
    run(service.coordinate_incident(_incident()))
    result = run(service.reassign_incident("INC-1024", "Facilities"))
    assert result.assigned_team == "Facilities"
    assert "Reassigned" in (result.slack_reply or "")


def test_escalate_does_not_recalculate_risk():
    service = _service()
    incident = _incident()
    run(service.coordinate_incident(incident))
    result = run(service.escalate_incident("INC-1024", mapping=incident))
    assert result.status == STATUS_ESCALATED
    second = run(service.escalate_incident("INC-1024", mapping=incident))
    assert second.status == STATUS_ESCALATED
    assert "already" in (second.slack_reply or "").lower()


def test_arbitrary_thread_text_ignored():
    service = _service()
    posted = run(service.coordinate_incident(_incident()))
    result = run(
        service.handle_thread_event(
            {"thread_ts": posted.slack_thread_ts, "text": "We are checking this now.", "user": "U1", "ts": "9.0"}
        )
    )
    assert result is None
    assert service.store.get("INC-1024").status == STATUS_ASSIGNED


def test_bot_loop_prevention():
    service = _service()
    posted = run(service.coordinate_incident(_incident()))
    result = run(
        service.handle_thread_event(
            {
                "thread_ts": posted.slack_thread_ts,
                "text": "resolved",
                "user": "B123",
                "subtype": "bot_message",
                "bot_id": "B123",
            }
        )
    )
    assert result is None


def test_slack_retry_idempotent():
    service = _service()
    posted = run(service.coordinate_incident(_incident()))
    event = {"thread_ts": posted.slack_thread_ts, "text": "accept", "user": "U1", "event_id": "same"}
    first = run(service.handle_thread_event(event))
    second = run(service.handle_thread_event(event))
    assert first.status == STATUS_ACCEPTED
    assert second is not None
    assert second.coordination_error == "duplicate_slack_event"


def test_coordinate_twice_one_top_level_post():
    client = FakeSlackClient()
    service = _service(client)
    run(service.coordinate_incident(_incident()))
    run(service.coordinate_incident(_incident()))
    assert len(client.posts) == 1
    assert len(client.updates) == 1


def test_slack_failure_does_not_claim_success():
    client = FakeSlackClient()
    client.fail = "timeout"
    result = run(_service(client).coordinate_incident(_incident()))
    assert result.posted is False
    assert result.coordination_delivery_status == "Failed"
    assert result.coordination_error is not None


def test_repository_failure_on_accept():
    repo = FakeRepo()
    service = _service(repo=repo)
    run(service.coordinate_incident(_incident()))
    repo.fail_update = True
    result = run(service.accept_incident("INC-1024"))
    assert result.coordination_error == "repository_update_failed"
    assert result.status == STATUS_ASSIGNED
    assert "retry" in (result.slack_reply or "").lower()


def test_stale_accept_after_resolved():
    service = _service()
    run(service.coordinate_incident(_incident()))
    run(service.accept_incident("INC-1024"))
    run(service.update_incident_status("INC-1024", STATUS_IN_PROGRESS))
    run(service.update_incident_status("INC-1024", STATUS_RESOLVED))
    stale = run(
        service.handle_interactive_action(
            {"trigger_id": "old", "actions": [{"action_id": ACTION_ACCEPT, "value": "INC-1024"}]}
        )
    )
    assert stale.status == STATUS_RESOLVED
    assert stale.coordination_error == "invalid_status_transition"


def test_sanitize_mass_mentions():
    text = sanitize_slack_text("Electrical issue <!channel> everyone come now @here")
    assert "<!channel>" not in text
    assert "@here" not in text
    assert "mention-removed" in text


def test_missing_incident_id():
    result = run(_service().coordinate_incident({"hazard_category": "electrical"}))
    assert result.coordination_error == "incident_not_found"
    assert result.posted is False


def test_parse_unknown_reassign():
    parsed = parse_thread_command("reassign: ../../admin")
    assert parsed is not None
    assert parsed.get("invalid") == "1"


def test_missing_fields_still_post():
    client = FakeSlackClient()
    result = run(
        _service(client).coordinate_incident(
            _incident(location=None, people_exposed=None, risk={"level": "Low", "explanation": None})
        )
    )
    assert result.posted is True
    blob = json.dumps(client.posts[0]["blocks"])
    assert "Unknown" in blob
    assert "*People exposed:* 0" not in blob
    assert "*People exposed:* Unknown" in blob


def test_people_exposed_zero_is_not_unknown():
    blocks = build_incident_blocks(
        incident_id="INC-1",
        category="electrical",
        location="Bay 2",
        description="Guard missing",
        people_exposed=0,
        risk_level="Low",
        risk_explanation="Isolated",
        recommended_action="normal_incident_processing",
        assigned_team="Facilities",
        duplicate_count=1,
    )
    blob = json.dumps(blocks)
    assert "*People exposed:* 0" in blob
    assert "*People exposed:* Unknown" not in blob


def test_channel_not_configured():
    slack = SlackHandler(client=FakeSlackClient(), destinations={})
    service = CoordinationService(slack=slack, store=MemoryCoordinationStore(), destinations={})
    result = run(service.coordinate_incident(_incident()))
    assert result.posted is False
    assert result.coordination_error == "slack_channel_not_configured"


def test_channel_not_found_is_permanent():
    client = FakeSlackClient()
    client.fail = "channel_not_found"
    result = run(_service(client).coordinate_incident(_incident()))
    assert result.posted is False
    assert result.coordination_error == "channel_not_found"
    assert result.coordination_delivery_status == "Failed"


def test_inspection_request_posts_slack_note_without_status_change():
    client = FakeSlackClient()
    repo = FakeRepo()
    service = _service(client, repo)
    result = run(
        service.request_inspection(
            {
                "location": "Chemical Storage Room",
                "category": "chemical",
                "reason": "3 chemical leak reports detected in 25 days.",
                "recommendation": "Schedule safety inspection.",
            }
        )
    )
    assert result.posted is True
    assert result.message_type == "inspection_request"
    assert repo.statuses == []
    blob = json.dumps(client.posts[0])
    assert "Preventive Inspection Request" in blob
    assert "Chemical Storage Room" in blob
    assert "Attention Needed" in blob
    assert client.posts[0]["channel"] == "C-LAB"
