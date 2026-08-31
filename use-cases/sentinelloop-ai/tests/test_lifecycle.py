"""Canonical lifecycle transition tests. Complements tests/test_incident_lifecycle.py."""

from __future__ import annotations

import pytest

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

ALLOWED = list(zip(LIFECYCLE, LIFECYCLE[1:]))


@pytest.mark.parametrize(("current", "target"), ALLOWED)
def test_allowed_forward_transitions(current, target):
    assert can_transition(current, target)
    assert validate_status_transition(current, target) == "ok"


def test_lifecycle_names_match_product_order():
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


def test_worker_reopen_from_resolved_to_in_progress():
    assert validate_status_transition(STATUS_RESOLVED, STATUS_IN_PROGRESS) == "ok"


def test_reject_new_to_closed():
    assert validate_status_transition(STATUS_NEW, STATUS_CLOSED) == "invalid"
    assert not can_transition(STATUS_NEW, STATUS_CLOSED)


def test_reject_assigned_to_closed():
    assert validate_status_transition(STATUS_ASSIGNED, STATUS_CLOSED) == "invalid"
    assert not can_transition(STATUS_ASSIGNED, STATUS_CLOSED)


def test_reject_closed_to_resolved():
    assert validate_status_transition(STATUS_CLOSED, STATUS_RESOLVED) == "invalid"
    assert not can_transition(STATUS_CLOSED, STATUS_RESOLVED)
