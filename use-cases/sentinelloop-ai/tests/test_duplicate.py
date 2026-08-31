"""Required duplicate merge, escalation, and location-split tests.

Complements tests/test_duplicate_tools.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.conftest import FakeRepository
from tools.duplicate_tools import (
    DuplicateQuery,
    DuplicateResult,
    check_for_duplicate,
    escalate_duplicate_risk,
    handle_duplicate_match,
)


def _row(**kwargs) -> dict:
    data = {
        "id": uuid4(),
        "incident_ref": "INC-55",
        "location": "generator area",
        "hazard_category": "fire/smoke",
        "hazard_description": "fire near generator",
        "status": "IN_PROGRESS",
        "duplicate_count": 1,
        "current_risk_level": "LOW",
        "created_at": datetime.now(timezone.utc),
    }
    data.update(kwargs)
    return data


def test_duplicate_merge_increments_count_on_same_location_and_category():
    ident = uuid4()
    repo = FakeRepository(
        [
            _row(
                id=ident,
                location="Production Floor",
                hazard_category="machine",
                hazard_description="Hydraulic press has oil leakage",
            )
        ]
    )
    found = check_for_duplicate(
        DuplicateQuery(
            translated_text="Oil leaking from hydraulic machine",
            location="Production Floor",
            hazard_category="machine",
        ),
        repository=repo,
    )
    assert found.status == "confirmed"
    assert found.action == "reuse"
    assert found.canonical_incident_id == "INC-55"
    handled = handle_duplicate_match(repo, ident, result=found, current_risk_level="LOW")
    assert handled.duplicate_count >= 2
    assert repo.rows[0]["duplicate_count"] >= 2
    assert len(repo.rows) == 1


def test_duplicate_count_three_triggers_auto_escalation():
    ident = uuid4()
    repo = FakeRepository([_row(id=ident, duplicate_count=2, current_risk_level="LOW")])
    result = DuplicateResult(
        status="confirmed",
        action="reuse",
        canonical_uuid=ident,
        duplicate_count=2,
        similarity=0.9,
        decision_source="LOCAL_SIMILARITY",
        matching_fields=["category", "location", "description"],
    )
    handled = handle_duplicate_match(repo, ident, result=result, current_risk_level="LOW")
    assert handled.duplicate_count == 3
    assert handled.escalated is True
    assert handled.new_risk_level == "MEDIUM"
    assert repo.rows[0]["current_risk_level"] == "MEDIUM"
    messages = [
        getattr(item, "message", None) if not isinstance(item, dict) else item.get("message") for item in repo.updates
    ]
    assert "Priority increased — reported by multiple workers." in messages
    types = [
        getattr(item, "update_type", None) if not isinstance(item, dict) else item.get("update_type")
        for item in repo.updates
    ]
    assert "duplicate_threshold_reached" in types


def test_duplicate_escalation_writes_priority_event():
    ident = uuid4()
    repo = FakeRepository([_row(id=ident, current_risk_level="MEDIUM")])
    nxt = escalate_duplicate_risk(repo, ident, current_risk="MEDIUM", count=3)
    assert nxt == "HIGH"
    assert any(
        (getattr(item, "update_type", None) if not isinstance(item, dict) else item.get("update_type"))
        == "duplicate_threshold_reached"
        for item in repo.updates
    )


def test_similar_reports_at_different_locations_are_separate_incidents():
    repo = FakeRepository(
        [_row(location="Lab B", hazard_description="oil leaking from hydraulic machine", hazard_category="machine")]
    )
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="oil leaking from hydraulic machine",
            location="Production Floor",
            hazard_category="machine",
        ),
        repository=repo,
    )
    assert result.status == "none"
    assert result.action == "create_new"
    assert result.canonical_incident_id is None
