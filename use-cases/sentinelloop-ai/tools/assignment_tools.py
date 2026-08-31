"""Deterministic assignment routing. No LLM. No Slack API calls."""

from __future__ import annotations

import os
from typing import Any

TEAM_MAPPING = {
    "electrical": "Electrical Maintenance",
    "chemical": "Lab Safety Team",
    "machine": "Mechanical Maintenance",
    "missing PPE": "Safety Supervisor",
    "fire/smoke": "Emergency Response Team",
    "other": "Facilities",
}

DEFAULT_TEAM = "Facilities"

VALID_TEAMS = {
    "Electrical Maintenance",
    "Lab Safety Team",
    "Mechanical Maintenance",
    "Safety Supervisor",
    "Emergency Response Team",
    "Facilities",
}

STATUS_ASSIGNED = "Assigned"
STATUS_ACCEPTED = "Accepted"
STATUS_IN_PROGRESS = "In Progress"
STATUS_RESOLVED = "Resolved"
STATUS_ESCALATED = "Escalated"

COORDINATION_STATUSES = (
    STATUS_ASSIGNED,
    STATUS_ACCEPTED,
    STATUS_IN_PROGRESS,
    STATUS_RESOLVED,
    STATUS_ESCALATED,
)

VALID_TRANSITIONS = {
    STATUS_ASSIGNED: {STATUS_ACCEPTED, STATUS_IN_PROGRESS, STATUS_ESCALATED},
    STATUS_ACCEPTED: {STATUS_IN_PROGRESS, STATUS_ESCALATED, STATUS_RESOLVED},
    STATUS_IN_PROGRESS: {STATUS_RESOLVED, STATUS_ESCALATED},
    STATUS_ESCALATED: {STATUS_IN_PROGRESS, STATUS_RESOLVED},
    STATUS_RESOLVED: set(),
}

IDEMPOTENT_NOOPS = {
    (STATUS_ACCEPTED, STATUS_ACCEPTED),
    (STATUS_IN_PROGRESS, STATUS_IN_PROGRESS),
    (STATUS_RESOLVED, STATUS_RESOLVED),
    (STATUS_ESCALATED, STATUS_ESCALATED),
    (STATUS_ASSIGNED, STATUS_ASSIGNED),
}

INCIDENT_STATUS_MAP = {
    STATUS_ASSIGNED: "ASSIGNED",
    STATUS_ACCEPTED: "ASSIGNED",
    STATUS_IN_PROGRESS: "IN_PROGRESS",
    STATUS_RESOLVED: "RESOLVED",
    STATUS_ESCALATED: "ESCALATED",
}

_CATEGORY_ALIASES = {
    "electrical": "electrical",
    "electric": "electrical",
    "electricity": "electrical",
    "fire": "fire/smoke",
    "smoke": "fire/smoke",
    "fire/smoke": "fire/smoke",
    "fire-smoke": "fire/smoke",
    "fire_smoke": "fire/smoke",
    "chemical": "chemical",
    "machine": "machine",
    "machinery": "machine",
    "missing ppe": "missing PPE",
    "ppe": "missing PPE",
    "slip/trip": "slip/trip",
    "structural": "structural",
    "unsafe behaviour": "unsafe behaviour",
    "unsafe behavior": "unsafe behaviour",
    "other": "other",
}

_DESTINATION_ENV = {
    "Electrical Maintenance": "SLACK_CHANNEL_ELECTRICAL_MAINTENANCE",
    "Lab Safety Team": "SLACK_CHANNEL_LAB_SAFETY",
    "Mechanical Maintenance": "SLACK_CHANNEL_MECHANICAL_MAINTENANCE",
    "Safety Supervisor": "SLACK_CHANNEL_SAFETY_SUPERVISOR",
    "Emergency Response Team": "SLACK_CHANNEL_EMERGENCY_RESPONSE",
    "Facilities": "SLACK_CHANNEL_FACILITIES",
}

ESCALATION_ENV = "SLACK_ESCALATION_CHANNEL"


def normalize_hazard_category(category: str | None) -> str:
    if category is None or str(category).strip() == "":
        return ""
    raw = str(category).strip().lower()
    return _CATEGORY_ALIASES.get(raw, raw)


def get_assigned_team(category: str | None) -> str:
    normalized = normalize_hazard_category(category)
    return TEAM_MAPPING.get(normalized, DEFAULT_TEAM)


def resolve_team_name(candidate: str | None) -> str | None:
    if not candidate:
        return None
    raw = str(candidate).strip()
    for team in VALID_TEAMS:
        if team.lower() == raw.lower():
            return team
    return None


def load_team_destinations(environ: dict[str, str] | None = None) -> dict[str, str]:
    env = environ if environ is not None else os.environ
    destinations: dict[str, str] = {}
    for team, key in _DESTINATION_ENV.items():
        value = (env.get(key) or "").strip()
        if value:
            destinations[team] = value
    return destinations


def resolve_team_destination(
    team: str,
    destinations: dict[str, str] | None = None,
    environ: dict[str, str] | None = None,
) -> str | None:
    mapping = destinations if destinations is not None else load_team_destinations(environ)
    return mapping.get(team)


def resolve_escalation_destination(
    destinations: dict[str, str] | None = None,
    environ: dict[str, str] | None = None,
) -> str | None:
    env = environ if environ is not None else os.environ
    configured = (env.get(ESCALATION_ENV) or "").strip()
    if configured:
        return configured
    mapping = destinations if destinations is not None else load_team_destinations(environ)
    return mapping.get("Emergency Response Team") or mapping.get(DEFAULT_TEAM)


def validate_status_transition(current: str, target: str) -> str:
    """Return 'ok', 'noop', or 'invalid'."""
    if (current, target) in IDEMPOTENT_NOOPS:
        return "noop"
    allowed = VALID_TRANSITIONS.get(current, set())
    if target in allowed:
        return "ok"
    return "invalid"


def format_category_display(category: str | None) -> str:
    if category is None or str(category).strip() == "":
        return "Unknown"
    normalized = normalize_hazard_category(category)
    labels = {
        "electrical": "Electrical",
        "chemical": "Chemical",
        "machine": "Machine",
        "missing PPE": "Missing PPE",
        "fire/smoke": "Fire/smoke",
        "other": "Other",
        "slip/trip": "Slip/trip",
        "structural": "Structural",
        "unsafe behaviour": "Unsafe behaviour",
    }
    return labels.get(normalized, str(category).strip())


def format_recommended_action(value: str | None) -> str:
    if not value:
        return "Unknown"
    return str(value).replace("_", " ").strip().capitalize()


def extract_risk(mapping: dict[str, Any]) -> tuple[str | None, str | None]:
    nested = mapping.get("risk")
    if isinstance(nested, dict):
        level = nested.get("level") or nested.get("final_level")
        explanation = nested.get("explanation")
        if level or explanation:
            return (str(level) if level else None, str(explanation) if explanation else None)
    level = mapping.get("risk_level") or mapping.get("level")
    explanation = mapping.get("risk_explanation") or mapping.get("explanation")
    return (
        str(level) if level else None,
        str(explanation) if explanation else None,
    )
