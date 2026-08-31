"""Local emergency keyword gate. No network, database, or LLM calls."""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from guardrails.emergency_keywords import (
    ALWAYS_TRIGGER,
    CONTEXTUAL_WORDS,
    DUPLICATE_WINDOW_SECONDS,
    EMERGENCY_CATEGORY,
    EMERGENCY_KEYWORDS,
    EMERGENCY_RISK_LEVEL,
    FALSE_POSITIVE_CONTEXT,
    IMMEDIATE_CONTEXT,
    LOCATION_HINTS,
    NEGATION_CONTEXT,
    RISK_EXPLANATION,
    WORKER_EMERGENCY_REPLY,
)

log = logging.getLogger("sentinelloop.emergency_bypass")

_WHITESPACE = re.compile(r"\s+", re.UNICODE)
_LATIN_PUNCT = re.compile(r"[^\w\s\u0D80-\u0DFF\u0B80-\u0BFF🆘🔥⚠🚨❗]", re.UNICODE)
_NEAR_LOCATION = re.compile(
    r"\b(?:near|at|in)\s+([a-z0-9][a-z0-9 \-]{1,48})",
    re.IGNORECASE,
)
_SINHALA = re.compile(r"[\u0D80-\u0DFF]")
_TAMIL = re.compile(r"[\u0B80-\u0BFF]")

_PHRASES: tuple[str, ...] = tuple(
    sorted(
        {
            str(item).casefold()
            for group in EMERGENCY_KEYWORDS.values()
            for item in group
            if item and item not in EMERGENCY_KEYWORDS["emoji"]
        },
        key=len,
        reverse=True,
    )
)
_EMOJIS: tuple[str, ...] = tuple(EMERGENCY_KEYWORDS["emoji"])
_ALWAYS = frozenset(item.casefold() for item in ALWAYS_TRIGGER)
_CONTEXTUAL = frozenset(item.casefold() for item in CONTEXTUAL_WORDS)
_FALSE_POSITIVE = tuple(item.casefold() for item in FALSE_POSITIVE_CONTEXT)
_IMMEDIATE = tuple(item.casefold() for item in IMMEDIATE_CONTEXT)
_NEGATION = tuple(item.casefold() for item in NEGATION_CONTEXT)

_STATS: dict[str, Any] = {
    "alerts_today": 0,
    "response_ms_sum": 0.0,
    "response_count": 0,
    "active_critical": 0,
    "day": None,
    "records": [],
}


@dataclass(frozen=True)
class EmergencyMatch:
    triggered: bool
    trigger_keyword: str | None = None
    execution_time_ms: float = 0.0
    possible_location: str | None = None
    language: str = "en"


@dataclass
class EmergencyRecord:
    incident_ref: str
    incident_uuid: str | None
    trigger_keyword: str | None
    channel: str
    detection_time: str
    response_time_ms: float | None
    location: str | None
    lifecycle: str
    enrichment_completed: bool = False
    messages: list[str] = field(default_factory=list)


def reset_emergency_stats() -> None:
    _STATS.update(
        {
            "alerts_today": 0,
            "response_ms_sum": 0.0,
            "response_count": 0,
            "active_critical": 0,
            "day": None,
            "records": [],
        }
    )


def emergency_stats() -> dict[str, Any]:
    count = int(_STATS["response_count"])
    avg_ms = float(_STATS["response_ms_sum"]) / count if count else None
    return {
        "emergency_alerts_today": int(_STATS["alerts_today"]),
        "average_response_time_ms": avg_ms,
        "average_response_time": _format_seconds(avg_ms / 1000.0 if avg_ms is not None else None),
        "active_critical_incidents": int(_STATS["active_critical"]),
        "records": list(_STATS["records"]),
    }


def record_emergency_alert(
    *,
    incident_ref: str,
    incident_uuid: str | None = None,
    trigger_keyword: str | None = None,
    channel: str = "whatsapp",
    detection_time: str | None = None,
    response_time_ms: float | None = None,
    location: str | None = None,
    lifecycle: str = "Emergency Detected",
    message: str | None = None,
) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if _STATS["day"] != today:
        _STATS["day"] = today
        _STATS["alerts_today"] = 0
        _STATS["response_ms_sum"] = 0.0
        _STATS["response_count"] = 0
    _STATS["alerts_today"] = int(_STATS["alerts_today"]) + 1
    if response_time_ms is not None:
        _STATS["response_ms_sum"] = float(_STATS["response_ms_sum"]) + float(response_time_ms)
        _STATS["response_count"] = int(_STATS["response_count"]) + 1
    _STATS["active_critical"] = int(_STATS["active_critical"]) + 1
    _STATS["records"].append(
        EmergencyRecord(
            incident_ref=incident_ref,
            incident_uuid=incident_uuid,
            trigger_keyword=trigger_keyword,
            channel=channel,
            detection_time=detection_time or datetime.now(timezone.utc).isoformat(),
            response_time_ms=response_time_ms,
            location=location,
            lifecycle=lifecycle,
            messages=[message] if message else [],
        )
    )


def mark_emergency_enrichment(incident_ref: str) -> None:
    for row in _STATS["records"]:
        if row.incident_ref == incident_ref:
            row.enrichment_completed = True
            if row.lifecycle == "Emergency Detected":
                row.lifecycle = "Critical Review"


def mark_emergency_lifecycle(incident_ref: str, lifecycle: str) -> None:
    for row in _STATS["records"]:
        if row.incident_ref == incident_ref:
            row.lifecycle = lifecycle
            if lifecycle in {"Resolved", "Closed"}:
                _STATS["active_critical"] = max(0, int(_STATS["active_critical"]) - 1)


def attach_emergency_message(incident_ref: str, message: str) -> None:
    for row in _STATS["records"]:
        if row.incident_ref == incident_ref:
            row.messages.append(message)
            return


def _format_seconds(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 10:
        return f"{value:.1f} seconds"
    return f"{int(round(value))} seconds"


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = _LATIN_PUNCT.sub(" ", folded)
    return _WHITESPACE.sub(" ", folded).strip()


def detect_emergency_language(raw_text: str | None) -> str:
    blob = raw_text or ""
    if _SINHALA.search(blob):
        return "si"
    if _TAMIL.search(blob):
        return "ta"
    return "en"


def extract_possible_location(raw_text: str | None) -> str | None:
    """Fast local location hint. Must not delay the emergency path."""
    blob = _normalize(raw_text or "")
    if not blob:
        return None
    for hint in LOCATION_HINTS:
        if hint in blob:
            return hint
    match = _NEAR_LOCATION.search(blob)
    if match:
        value = match.group(1).strip(" -")
        value = re.sub(r"\s+", " ", value)
        if value:
            return value
    return None


def worker_emergency_reply(language: str | None = None) -> str:
    key = (language or "en").strip().lower()
    if key in {"si", "sinhala"}:
        return WORKER_EMERGENCY_REPLY["si"]
    if key in {"ta", "tamil"}:
        return WORKER_EMERGENCY_REPLY["ta"]
    return WORKER_EMERGENCY_REPLY["en"]


def format_emergency_slack_alert(
    *,
    source: str,
    message: str,
    incident_ref: str | None = None,
    location: str | None = None,
) -> str:
    quoted = (message or "").strip() or "(empty)"
    lines = [
        "🚨 EMERGENCY ALERT",
        "",
        "Immediate assistance required.",
        "",
        "Source:",
        source.title() if source else "Unknown",
        "",
        "Message:",
        f'"{quoted}"',
        "",
        "Risk:",
        EMERGENCY_RISK_LEVEL,
        "",
        "AI triage:",
        "Bypassed",
    ]
    if incident_ref:
        lines.extend(["", "Incident:", incident_ref])
    if location:
        lines.extend(["", "Location:", location])
    return "\n".join(lines)


def _has_any(haystack: str, needles: tuple[str, ...]) -> bool:
    return any(item in haystack for item in needles)


def _word_present(haystack: str, word: str) -> bool:
    if not word.isascii():
        return word in haystack
    if " " in word:
        return word in haystack
    return re.search(rf"\b{re.escape(word)}\b", haystack) is not None


def detect_emergency(raw_text: str | None) -> EmergencyMatch:
    started = time.perf_counter()
    original = raw_text if isinstance(raw_text, str) else ""
    if not original.strip():
        return EmergencyMatch(triggered=False, execution_time_ms=(time.perf_counter() - started) * 1000)

    for emoji in _EMOJIS:
        if emoji in original:
            location = extract_possible_location(original)
            return EmergencyMatch(
                triggered=True,
                trigger_keyword=emoji,
                execution_time_ms=(time.perf_counter() - started) * 1000,
                possible_location=location,
                language=detect_emergency_language(original),
            )

    normalized = _normalize(original)
    if not normalized:
        return EmergencyMatch(triggered=False, execution_time_ms=(time.perf_counter() - started) * 1000)

    matched: str | None = None
    always = False
    for phrase in _PHRASES:
        if _word_present(normalized, phrase):
            matched = phrase
            if phrase in _ALWAYS:
                always = True
                break

    if matched is None:
        return EmergencyMatch(
            triggered=False,
            execution_time_ms=(time.perf_counter() - started) * 1000,
            language=detect_emergency_language(original),
        )

    suppressed = _has_any(normalized, _FALSE_POSITIVE)
    immediate = always or _has_any(normalized, _IMMEDIATE)
    negated = _has_any(normalized, _NEGATION) and not immediate
    contextual = matched in _CONTEXTUAL

    triggered = True
    if negated and not always:
        triggered = False
    elif contextual and suppressed and not immediate:
        triggered = False

    return EmergencyMatch(
        triggered=triggered,
        trigger_keyword=matched if triggered else None,
        execution_time_ms=(time.perf_counter() - started) * 1000,
        possible_location=extract_possible_location(original) if triggered else None,
        language=detect_emergency_language(original),
    )


def is_emergency_trigger(raw_text: str | None) -> bool:
    """Return True when the worker text is an immediate life-safety cue.

    Pure and deterministic: no network, database, or LLM calls.
    """
    return detect_emergency(raw_text).triggered


def emergency_audit_payload(
    *,
    triggered: bool,
    trigger_keyword: str | None,
    detection_time: str,
    response_time_ms: float | None = None,
    possible_location: str | None = None,
    enrichment_completed: bool = False,
    repeated: bool = False,
) -> dict[str, Any]:
    return {
        "triggered": triggered,
        "trigger_keyword": trigger_keyword,
        "detection_time": detection_time,
        "bypass_used": True,
        "normal_ai_delayed": True,
        "response_time_ms": response_time_ms,
        "possible_location": possible_location,
        "later_enrichment": "Completed" if enrichment_completed else "Pending",
        "repeated": repeated,
        "risk_explanation": RISK_EXPLANATION,
        "category": EMERGENCY_CATEGORY,
        "risk_level": EMERGENCY_RISK_LEVEL,
        "duplicate_window_seconds": DUPLICATE_WINDOW_SECONDS,
    }
