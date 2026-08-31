"""Canonical incident lifecycle for SentinelLoop.

Display names are the product lifecycle. Repository persistence uses the
uppercase SPEC strings via ``to_repository_status``.
"""

from __future__ import annotations

STATUS_NEW = "New"
STATUS_VALIDATING = "Validating"
STATUS_ASSESSED = "Assessed"
STATUS_ASSIGNED = "Assigned"
STATUS_ACCEPTED = "Accepted"
STATUS_IN_PROGRESS = "In Progress"
STATUS_AWAITING_VERIFICATION = "Awaiting Verification"
STATUS_RESOLVED = "Resolved"
STATUS_CLOSED = "Closed"

LIFECYCLE = (
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

VALID_TRANSITIONS = {
    STATUS_NEW: {STATUS_VALIDATING},
    STATUS_VALIDATING: {STATUS_ASSESSED},
    STATUS_ASSESSED: {STATUS_ASSIGNED},
    STATUS_ASSIGNED: {STATUS_ACCEPTED, STATUS_IN_PROGRESS},
    STATUS_ACCEPTED: {STATUS_IN_PROGRESS},
    STATUS_IN_PROGRESS: {STATUS_AWAITING_VERIFICATION, STATUS_RESOLVED},
    STATUS_AWAITING_VERIFICATION: {STATUS_RESOLVED, STATUS_IN_PROGRESS, STATUS_CLOSED},
    STATUS_RESOLVED: {STATUS_CLOSED, STATUS_IN_PROGRESS},
    STATUS_CLOSED: set(),
}

IDEMPOTENT_NOOPS = {(status, status) for status in LIFECYCLE}

REPOSITORY_STATUS_MAP = {
    STATUS_NEW: "REPORTED",
    STATUS_VALIDATING: "ASSESSING",
    STATUS_ASSESSED: "OPEN",
    STATUS_ASSIGNED: "ASSIGNED",
    STATUS_ACCEPTED: "ASSIGNED",
    STATUS_IN_PROGRESS: "IN_PROGRESS",
    STATUS_AWAITING_VERIFICATION: "AWAITING_VERIFICATION",
    STATUS_RESOLVED: "RESOLVED",
    STATUS_CLOSED: "CLOSED",
}

_FROM_REPOSITORY = {
    "REPORTED": STATUS_NEW,
    "NEW": STATUS_NEW,
    "ASSESSING": STATUS_VALIDATING,
    "VALIDATING": STATUS_VALIDATING,
    "OPEN": STATUS_ASSESSED,
    "ASSESSED": STATUS_ASSESSED,
    "ASSIGNED": STATUS_ASSIGNED,
    "ACCEPTED": STATUS_ACCEPTED,
    "IN_PROGRESS": STATUS_IN_PROGRESS,
    "AWAITING_VERIFICATION": STATUS_AWAITING_VERIFICATION,
    "RESOLVED": STATUS_RESOLVED,
    "CLOSED": STATUS_CLOSED,
    "REOPENED": STATUS_IN_PROGRESS,
}


def to_repository_status(status: str) -> str:
    return REPOSITORY_STATUS_MAP.get(status, status)


def to_display_status(status: str | None) -> str | None:
    if status is None or str(status).strip() == "":
        return None
    raw = str(status).strip()
    if raw in LIFECYCLE:
        return raw
    return _FROM_REPOSITORY.get(raw.upper().replace(" ", "_"), raw)


def can_transition(current_status: str, target_status: str) -> bool:
    current = to_display_status(current_status) or current_status
    target = to_display_status(target_status) or target_status
    if (current, target) in IDEMPOTENT_NOOPS:
        return True
    return target in VALID_TRANSITIONS.get(current, set())


def validate_status_transition(current_status: str, target_status: str) -> str:
    """Return 'ok', 'noop', or 'invalid'."""
    current = to_display_status(current_status) or current_status
    target = to_display_status(target_status) or target_status
    if (current, target) in IDEMPOTENT_NOOPS:
        return "noop"
    if target in VALID_TRANSITIONS.get(current, set()):
        return "ok"
    return "invalid"
