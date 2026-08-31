"""Deterministic emergency keyword gate.

Runs before clarification, duplicate matching, and normal intake so active
life-safety reports are not paused for missing location text.
Does not score risk, assign teams, or send worker guidance.
"""

from __future__ import annotations

import re

log_name = "sentinelloop.emergency_bypass"

_EMERGENCY_CUES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfire\s+now\b", re.I),
    re.compile(r"\bon\s+fire\b", re.I),
    re.compile(r"\b(fire|flames?|burning)\b", re.I),
    re.compile(r"\bchemical\s+leak(ing)?\b", re.I),
    re.compile(r"\b(acid|chemical)\b.{0,24}\b(spill|leak|leaking)\b", re.I),
    re.compile(r"\bmachine\s+explosion\b", re.I),
    re.compile(r"\bexplod(e|ing|sion)\b", re.I),
    re.compile(r"\belectric(al)?\s+shock\b", re.I),
    re.compile(r"\blive\s+(wire|cable)\b", re.I),
    re.compile(r"\bheavy\s+smoke\b", re.I),
    re.compile(r"\bsmoke\s+coming\b", re.I),
    re.compile(r"\bunconscious\b", re.I),
    re.compile(r"\btrapped\b", re.I),
    re.compile(r"\bcollaps(e|ing)\b", re.I),
)

_NEGATION = re.compile(
    r"\b(no|not|never|stopped|fixed|repaired|resolved|yesterday|last week|no longer)\b",
    re.I,
)


def is_emergency_trigger(text: str | None) -> bool:
    """Return True when the worker text is an immediate life-safety cue."""
    blob = (text or "").strip()
    if not blob:
        return False
    if _NEGATION.search(blob) and not re.search(r"\b(still|now|currently)\b", blob, re.I):
        return False
    return any(pattern.search(blob) for pattern in _EMERGENCY_CUES)
