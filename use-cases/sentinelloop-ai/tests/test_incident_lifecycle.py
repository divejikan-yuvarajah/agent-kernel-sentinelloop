"""Canonical lifecycle tests. No network."""

from __future__ import annotations

from tools.lifecycle import (
    LIFECYCLE,
    STATUS_ACCEPTED,
    STATUS_ASSESSED,
    STATUS_ASSIGNED,
    STATUS_AWAITING_VERIFICATION,
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_NEW,
    STATUS_RESOLVED,
    STATUS_VALIDATING,
    can_transition,
    validate_status_transition,
)


def test_canonical_lifecycle_names():
    assert LIFECYCLE == (
        STATUS_NEW,
        STATUS_VALIDATING,
        STATUS_ASSESSED,
        STATUS_ASSIGNED,
        STATUS_ACCEPTED,
        STATUS_IN_PROGRESS,
        STATUS_AWAITING_VERIFICATION,
        STATUS_RESOLVED,
        STATUS_CLOSED,
    )
    assert LIFECYCLE == (
        "New",
        "Validating",
        "Assessed",
        "Assigned",
        "Accepted",
        "In Progress",
        "Awaiting Verification",
        "Resolved",
        "Closed",
    )
    joined = " ".join(LIFECYCLE)
    assert "Pending Verification" not in joined
    assert "Completed" not in joined
    assert "Verified" not in joined


def test_happy_path_transitions():
    path = list(zip(LIFECYCLE, LIFECYCLE[1:]))
    for current, target in path:
        assert can_transition(current, target)
        assert validate_status_transition(current, target) == "ok"


def test_worker_reopen_and_close():
    assert validate_status_transition(STATUS_RESOLVED, STATUS_CLOSED) == "ok"
    assert validate_status_transition(STATUS_RESOLVED, STATUS_IN_PROGRESS) == "ok"
    assert validate_status_transition(STATUS_AWAITING_VERIFICATION, STATUS_IN_PROGRESS) == "ok"


def test_invalid_closures():
    assert validate_status_transition(STATUS_NEW, STATUS_CLOSED) == "invalid"
    assert validate_status_transition(STATUS_ASSIGNED, STATUS_CLOSED) == "invalid"
    assert validate_status_transition(STATUS_CLOSED, STATUS_RESOLVED) == "invalid"
    assert validate_status_transition(STATUS_CLOSED, STATUS_ACCEPTED) == "invalid"
    assert not can_transition(STATUS_IN_PROGRESS, STATUS_CLOSED)
