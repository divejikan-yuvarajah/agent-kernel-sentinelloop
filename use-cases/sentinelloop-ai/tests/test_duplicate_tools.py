"""Duplicate detection tests. No live database or OpenRouter."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from tools.duplicate_tools import (
    DuplicateQuery,
    DuplicateResult,
    calculate_similarity,
    check_duplicate_incident,
    check_for_duplicate,
    duplicate_detection_stats,
    escalate_duplicate_risk,
    find_duplicate_incident,
    handle_duplicate_match,
    reset_duplicate_detection_stats,
)
from tools.model_router import ModelCallResult


class FakeRepo:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = list(rows or [])
        self.updates: list[object] = []
        self.field_updates: list[tuple] = []

    def list_incidents(self, filters=None):
        return list(self.rows)

    def get_incident(self, incident_id):
        for row in self.rows:
            if row.get("id") == incident_id:
                return type("Row", (), row)()
        return None

    def increment_duplicate_count(self, incident_id):
        for row in self.rows:
            if row.get("id") == incident_id:
                row["duplicate_count"] = int(row.get("duplicate_count") or 0) + 1
                return type("Row", (), row)()
        raise KeyError(incident_id)

    def update_incident_fields(self, incident_id, fields):
        self.field_updates.append((incident_id, fields))
        for row in self.rows:
            if row.get("id") == incident_id:
                row.update(fields)
                return type("Row", (), row)()
        raise KeyError(incident_id)

    def add_update(self, data) -> None:
        self.updates.append(data)


class FakeRouter:
    def __init__(self, content: str | Exception) -> None:
        self.content = content
        self.calls: list[tuple] = []

    async def __call__(self, role: str, messages: list, **kwargs):
        self.calls.append((role, messages, kwargs))
        if isinstance(self.content, Exception):
            raise self.content
        return ModelCallResult(content=self.content, model="mock/fast", role=role, paid=False)


def run(coro):
    return asyncio.run(coro)


def _row(**kwargs) -> dict:
    now = datetime.now(timezone.utc)
    data = {
        "id": uuid4(),
        "incident_ref": "INC-55",
        "location": "generator area",
        "hazard_category": "fire/smoke",
        "hazard_description": "fire near generator",
        "status": "IN_PROGRESS",
        "duplicate_count": 1,
        "current_risk_level": "LOW",
        "created_at": now,
    }
    data.update(kwargs)
    return data


@pytest.fixture(autouse=True)
def _reset_stats():
    reset_duplicate_detection_stats()
    yield
    reset_duplicate_detection_stats()


def test_similarity_exact_and_paraphrase():
    assert calculate_similarity("fire near generator", "fire near generator") == 1.0
    oil = calculate_similarity("Oil leaking from hydraulic machine", "Hydraulic press has oil leakage")
    assert oil >= 0.6
    smoke = calculate_similarity("Smoke coming from motor", "Motor producing smoke")
    assert smoke >= 0.6
    different = calculate_similarity("Oil leaking from hydraulic machine", "Electrical sparking at panel")
    assert different < 0.6


def test_no_duplicate():
    repo = FakeRepo([_row()])
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="slippery floor in cafeteria", location="cafeteria", hazard_category="slip/trip"
        ),
        repository=repo,
    )
    assert result.status == "none"
    assert result.action == "create_new"


def test_confirmed_duplicate_reuses_canonical_id():
    repo = FakeRepo(
        [
            _row(
                location="Production Floor",
                hazard_category="machine",
                hazard_description="Hydraulic press has oil leakage",
            )
        ]
    )
    result = find_duplicate_incident(
        {
            "translated_text": "Oil leaking from hydraulic machine",
            "location": "Production Floor",
            "hazard_category": "machine",
        },
        repository=repo,
    )
    assert result.status == "confirmed"
    assert result.action == "reuse"
    assert result.canonical_incident_id == "INC-55"
    assert result.decision_source == "LOCAL_SIMILARITY"
    assert result.preserve_status is True
    assert "location" in result.matching_fields
    assert "category" in result.matching_fields


def test_different_location_is_not_duplicate():
    repo = FakeRepo(
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


def test_different_hazard_same_location_is_not_duplicate():
    repo = FakeRepo(
        [_row(location="Bay 2", hazard_category="machine", hazard_description="oil leaking from hydraulic machine")]
    )
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="electrical sparking at panel b17",
            location="Bay 2",
            hazard_category="electrical",
        ),
        repository=repo,
    )
    assert result.status == "none"


def test_in_progress_status_preserved():
    repo = FakeRepo([_row(status="IN_PROGRESS")])
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="fire near generator",
            location="generator area",
            hazard_category="fire/smoke",
        ),
        repository=repo,
    )
    assert result.canonical_status == "In Progress"
    assert result.preserve_status is True
    assert result.action == "reuse"


def test_closed_without_recurrence_does_not_attach():
    repo = FakeRepo([_row(status="CLOSED")])
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="fire near generator last week", location="generator area", hazard_category="fire/smoke"
        ),
        repository=repo,
    )
    assert result.action == "create_new"
    assert result.canonical_incident_id is None


def test_resolved_incidents_ignored():
    repo = FakeRepo([_row(status="RESOLVED")])
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="fire near generator",
            location="generator area",
            hazard_category="fire/smoke",
        ),
        repository=repo,
    )
    assert result.status == "none"


def test_closed_with_still_present_reopens():
    repo = FakeRepo([_row(status="CLOSED")])
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="fire near generator still happening now",
            location="generator area",
            hazard_category="fire/smoke",
            is_active=True,
        ),
        repository=repo,
    )
    assert result.status == "confirmed"
    assert result.action == "reopen"
    assert result.canonical_incident_id == "INC-55"


def test_old_incident_outside_window_ignored():
    old = datetime.now(timezone.utc) - timedelta(days=10)
    repo = FakeRepo([_row(created_at=old)])
    result = check_for_duplicate(
        DuplicateQuery(
            translated_text="fire near generator",
            location="generator area",
            hazard_category="fire/smoke",
        ),
        repository=repo,
        window_hours=24,
    )
    assert result.status == "none"


def test_missing_description_safe_fallback():
    repo = FakeRepo([_row()])
    result = check_for_duplicate(
        DuplicateQuery(translated_text="  ", location="generator area", hazard_category="fire/smoke"),
        repository=repo,
    )
    assert result.status == "none"
    assert result.reason == "missing_description"


def test_compares_translated_text_only():
    repo = FakeRepo(
        [_row(hazard_description="Smoke coming from motor", location="Lab B", hazard_category="fire/smoke")]
    )
    result = check_for_duplicate(
        DuplicateQuery(
            raw_text="මෝටර් එකෙන් දුම් එනවා",
            translated_text="Motor producing smoke",
            location="Lab B",
            hazard_category="fire/smoke",
        ),
        repository=repo,
    )
    assert result.status == "confirmed"
    assert result.decision_source == "LOCAL_SIMILARITY"


def test_strong_match_skips_llm():
    repo = FakeRepo([_row()])
    router = FakeRouter("YES")
    result = run(
        check_duplicate_incident(
            DuplicateQuery(
                translated_text="fire near generator",
                location="generator area",
                hazard_category="fire/smoke",
            ),
            repository=repo,
            call_model_fn=router,
        )
    )
    assert result.status == "confirmed"
    assert result.decision_source == "LOCAL_SIMILARITY"
    assert router.calls == []
    stats = duplicate_detection_stats()
    assert stats["local_matches"] == 1
    assert stats["llm_checks"] == 0
    assert stats["avoided_duplicates"] == 1


def test_llm_verification_called_once_on_borderline(monkeypatch):
    monkeypatch.setattr("tools.duplicate_tools.calculate_similarity", lambda a, b: 0.5)
    repo = FakeRepo(
        [
            _row(incident_ref="INC-1", hazard_description="report one"),
            _row(incident_ref="INC-2", id=uuid4(), hazard_description="report two"),
        ]
    )
    router = FakeRouter("YES")
    result = run(
        check_duplicate_incident(
            DuplicateQuery(
                translated_text="borderline hazard text",
                location="generator area",
                hazard_category="fire/smoke",
            ),
            repository=repo,
            call_model_fn=router,
        )
    )
    assert result.status == "confirmed"
    assert result.decision_source == "AI_VERIFICATION"
    assert len(router.calls) == 1
    assert router.calls[0][0] == "role_fast"
    assert duplicate_detection_stats()["llm_checks"] == 1


def test_model_unavailable_falls_back_to_local(monkeypatch):
    monkeypatch.setattr("tools.duplicate_tools.calculate_similarity", lambda a, b: 0.5)
    repo = FakeRepo(
        [
            _row(incident_ref="INC-1"),
            _row(incident_ref="INC-2", id=uuid4()),
        ]
    )
    router = FakeRouter(RuntimeError("provider down"))
    result = run(
        check_duplicate_incident(
            DuplicateQuery(
                translated_text="borderline hazard text",
                location="generator area",
                hazard_category="fire/smoke",
            ),
            repository=repo,
            call_model_fn=router,
        )
    )
    assert result.action == "create_new"
    assert result.status == "possible"
    assert result.canonical_incident_id is None


def test_duplicate_count_increment_and_escalation():
    ident = uuid4()
    repo = FakeRepo(
        [_row(id=ident, duplicate_count=2, current_risk_level="LOW", hazard_description="fire near generator")]
    )
    result = DuplicateResult(
        status="confirmed",
        action="reuse",
        canonical_uuid=ident,
        duplicate_count=2,
        similarity=0.82,
        decision_source="LOCAL_SIMILARITY",
        matching_fields=["category", "location", "description"],
    )
    handled = handle_duplicate_match(repo, ident, result=result, current_risk_level="LOW")
    assert handled.duplicate_count == 3
    assert handled.escalated is True
    assert handled.new_risk_level == "MEDIUM"
    assert repo.rows[0]["current_risk_level"] == "MEDIUM"
    messages = [getattr(item, "message", None) for item in repo.updates]
    assert "Duplicate hazard detected from another worker report." in messages
    assert "Priority increased — reported by multiple workers." in messages
    types = [getattr(item, "update_type", None) for item in repo.updates]
    assert "duplicate_threshold_reached" in types


def test_escalation_never_exceeds_critical():
    ident = uuid4()
    repo = FakeRepo([_row(id=ident, current_risk_level="CRITICAL")])
    nxt = escalate_duplicate_risk(repo, ident, current_risk="CRITICAL", count=3)
    assert nxt == "CRITICAL"


def test_possible_duplicate_is_not_merged():
    repo = FakeRepo([_row(location="warehouse 1", hazard_description="oil on floor")])
    result = check_for_duplicate(
        DuplicateQuery(translated_text="something in warehouse", location="warehouse 9", hazard_category="slip/trip"),
        repository=repo,
    )
    assert result.status in {"none", "possible"}
    if result.status == "possible":
        assert result.action == "create_new"
        assert result.canonical_incident_id is None
