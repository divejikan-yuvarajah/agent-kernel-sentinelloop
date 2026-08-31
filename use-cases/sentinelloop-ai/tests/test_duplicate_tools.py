"""Prompt 14 duplicate-tools tests. No live database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tools.duplicate_tools import DuplicateQuery, check_for_duplicate, find_duplicate_incident


class FakeRepo:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows

    def list_incidents(self, filters=None):
        return list(self.rows)


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
        "created_at": now,
    }
    data.update(kwargs)
    return data


def test_no_duplicate():
    repo = FakeRepo([_row()])
    result = check_for_duplicate(
        DuplicateQuery(translated_text="slippery floor in cafeteria", location="cafeteria"),
        repository=repo,
    )
    assert result.status == "none"
    assert result.action == "create_new"


def test_confirmed_duplicate_reuses_canonical_id():
    repo = FakeRepo([_row()])
    result = find_duplicate_incident(
        {
            "translated_text": "generator area smoking",
            "location": "generator area",
            "hazard_category": "fire/smoke",
        },
        repository=repo,
    )
    assert result.status == "confirmed"
    assert result.action == "reuse"
    assert result.canonical_incident_id == "INC-55"
    assert result.preserve_status is True


def test_possible_duplicate_is_not_merged():
    repo = FakeRepo([_row(location="warehouse 1", hazard_description="oil on floor")])
    result = check_for_duplicate(
        DuplicateQuery(translated_text="something in warehouse", location="warehouse 9"),
        repository=repo,
    )
    assert result.status in {"none", "possible"}
    if result.status == "possible":
        assert result.action == "create_new"
        assert result.canonical_incident_id is None


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
        DuplicateQuery(translated_text="fire near generator last week", location="generator area"),
        repository=repo,
    )
    assert result.action == "create_new"
    assert result.canonical_incident_id is None


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
