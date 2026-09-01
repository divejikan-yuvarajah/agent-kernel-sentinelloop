"""Structured guardrail audit events. Never store API keys or private worker prompts."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from guardrails.config import load_guardrail_config

EVENT_PASSED = "guardrail_passed"
EVENT_FAILED = "guardrail_failed"
EVENT_GUIDANCE_BLOCKED = "guidance_blocked"
EVENT_PRIVACY_REDACTION = "privacy_redaction"
EVENT_CLOSURE_BLOCKED = "closure_blocked"
EVENT_BUDGET_BLOCKED = "budget_blocked"
EVENT_MODEL_ALLOWED = "model_call_allowed"
EVENT_MODEL_BLOCKED_BUDGET = "model_call_blocked_budget"
EVENT_BUDGET_WARNING = "budget_warning"

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "openai_api_key",
        "openrouter_api_key",
        "authorization",
        "slack_bot_token",
        "telegram_token",
        "system_prompt",
        "prompt",
        "messages",
    }
)


class GuardrailEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: str
    guardrail: str
    approved: bool = True
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    incident_id: str | None = None
    agent: str | None = None
    rule: str | None = None
    decision: str | None = None
    violations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


_LOCK = threading.Lock()
_EVENTS: deque[GuardrailEvent] | None = None


def _buffer() -> deque[GuardrailEvent]:
    global _EVENTS
    if _EVENTS is None:
        size = int(load_guardrail_config().get("event_buffer_size") or 500)
        _EVENTS = deque(maxlen=max(size, 50))
    return _EVENTS


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in _SECRET_KEYS or "token" in lowered and "usage" not in lowered:
                continue
            out[key] = _scrub(item)
        return out
    if isinstance(value, list):
        return [_scrub(item) for item in value[:40]]
    if isinstance(value, str) and len(value) > 400:
        return value[:400] + "…"
    return value


def emit_guardrail_event(
    event: str,
    *,
    guardrail: str,
    approved: bool = True,
    incident_id: str | None = None,
    agent: str | None = None,
    rule: str | None = None,
    decision: str | None = None,
    violations: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> GuardrailEvent:
    record = GuardrailEvent(
        event=event,
        guardrail=guardrail,
        approved=approved,
        incident_id=incident_id,
        agent=agent,
        rule=rule,
        decision=decision,
        violations=list(violations or []),
        metadata=_scrub(metadata or {}),
    )
    with _LOCK:
        _buffer().append(record)
    return record


def list_guardrail_events(
    *,
    incident_id: str | None = None,
    limit: int = 200,
) -> list[GuardrailEvent]:
    with _LOCK:
        items = list(_buffer())
    if incident_id:
        items = [item for item in items if item.incident_id == incident_id]
    if limit > 0:
        items = items[-limit:]
    return items


def guardrail_metrics() -> dict[str, int]:
    with _LOCK:
        items = list(_buffer())
    total = len(items)
    passed = sum(1 for item in items if item.approved)
    blocked = sum(1 for item in items if not item.approved)
    warnings = sum(1 for item in items if item.event == EVENT_BUDGET_WARNING)
    counts = {
        "total_validations": total,
        "passed": passed,
        "blocked": blocked,
        "warnings": warnings,
        "guidance_hallucinations": sum(1 for item in items if item.event == EVENT_GUIDANCE_BLOCKED),
        "privacy_attempts": sum(1 for item in items if item.event == EVENT_PRIVACY_REDACTION),
        "blocked_closures": sum(1 for item in items if item.event == EVENT_CLOSURE_BLOCKED),
        "budget_blocks": sum(1 for item in items if item.event in {EVENT_BUDGET_BLOCKED, EVENT_MODEL_BLOCKED_BUDGET}),
    }
    return counts


def reset_guardrail_events() -> None:
    with _LOCK:
        _buffer().clear()
