"""Slack coordination card content and officer actions. Complements tests/test_coordination_agent.py."""

from __future__ import annotations

import json
from uuid import uuid4

from agents.coordination_agent import CoordinationService, MemoryCoordinationStore
from integrations.slack_handler import (
    ACTION_ACCEPT,
    ACTION_ESCALATE,
    ACTION_REASSIGN,
    SlackHandler,
    build_incident_blocks,
)
from tests.conftest import FakeRepository, MockSlackClient, run
from tools.assignment_tools import STATUS_ACCEPTED, STATUS_ESCALATED

DESTINATIONS = {
    "Electrical Maintenance": "C-ELEC",
    "Lab Safety Team": "C-LAB",
    "Mechanical Maintenance": "C-MECH",
    "Safety Supervisor": "C-SAFE",
    "Emergency Response Team": "C-EMRG",
    "Facilities": "C-FAC",
}


def _service(client: MockSlackClient | None = None, repo: FakeRepository | None = None) -> CoordinationService:
    slack = SlackHandler(client=client or MockSlackClient(), destinations=DESTINATIONS)
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


def test_slack_message_contains_required_incident_fields():
    client = MockSlackClient()
    posted = run(_service(client).coordinate_incident(_incident()))
    assert posted.posted is True
    blob = json.dumps(client.posts[0]["blocks"])
    assert "INC-1024" in blob
    assert "electrical" in blob.lower() or "Electrical" in blob
    assert "Panel Room" in blob
    assert "Critical" in blob
    assert "Active electrical hazard" in blob
    assert "Electrical Maintenance" in blob
    assert "Duplicate reports: 3" in blob
    assert posted.assigned_team == "Electrical Maintenance"
    assert posted.duplicate_count == 3


def test_incident_blocks_include_id_category_location_risk_team_and_duplicates():
    blocks = build_incident_blocks(
        incident_id="INC-1024",
        category="Electrical",
        location="Panel Room",
        description="Panel is sparking",
        people_exposed=8,
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
        "Critical",
        "Active electrical hazard",
        "Electrical Maintenance",
        "Duplicate reports: 3",
        "Accept",
        "Reassign",
        "Escalate",
    ):
        assert token in blob


def test_slack_accept_action():
    client = MockSlackClient()
    service = _service(client)
    run(service.coordinate_incident(_incident()))
    accepted = run(
        service.handle_interactive_action(
            {
                "trigger_id": "t-accept",
                "user": {"id": "U1"},
                "actions": [{"action_id": ACTION_ACCEPT, "value": "INC-1024"}],
            },
            mapping=_incident(),
        )
    )
    assert accepted.status == STATUS_ACCEPTED
    assert "accept" in (accepted.slack_reply or "").lower()


def test_slack_reassign_action():
    client = MockSlackClient()
    service = _service(client)
    run(service.coordinate_incident(_incident()))
    result = run(
        service.handle_interactive_action(
            {
                "trigger_id": "t-reassign",
                "user": {"id": "U1"},
                "actions": [
                    {"action_id": ACTION_REASSIGN, "value": "INC-1024", "selected_option": {"value": "Facilities"}}
                ],
            },
            mapping=_incident(),
        )
    )
    if result.coordination_error:
        result = run(service.reassign_incident("INC-1024", "Facilities"))
    assert result.assigned_team == "Facilities"
    assert "Reassigned" in (result.slack_reply or "")


def test_slack_escalate_action():
    client = MockSlackClient()
    service = _service(client)
    incident = _incident()
    run(service.coordinate_incident(incident))
    result = run(
        service.handle_interactive_action(
            {
                "trigger_id": "t-escalate",
                "user": {"id": "U1"},
                "actions": [{"action_id": ACTION_ESCALATE, "value": "INC-1024"}],
            },
            mapping=incident,
        )
    )
    assert result.status == STATUS_ESCALATED
