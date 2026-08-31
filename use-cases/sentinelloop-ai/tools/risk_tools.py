"""Deterministic workplace safety risk engine.

The LLM may estimate severity and likelihood. It must never decide the
final risk level. ``calculate_risk`` owns the matrix, safety overrides,
and the explanation. This module is a pure function: no I/O, no LLM, no time.
"""

from __future__ import annotations

from typing import Any

LEVEL_LOW = "Low"
LEVEL_MEDIUM = "Medium"
LEVEL_HIGH = "High"
LEVEL_CRITICAL = "Critical"
RISK_LEVELS = (LEVEL_LOW, LEVEL_MEDIUM, LEVEL_HIGH, LEVEL_CRITICAL)

CRITICAL_ACTIVE_CATEGORIES = frozenset({"electrical", "fire/smoke", "chemical"})
EXPOSURE_BUMP_THRESHOLD = 5
RISK_POLICY_VERSION = "1.0"

REASON_INJURY = "already_injured"
REASON_CRITICAL_ACTIVE = "active_critical_category"
REASON_EXPOSURE = "people_exposed_gte_5"

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
}


class RiskInputError(ValueError):
    """Invalid input to ``calculate_risk``."""


def normalize_category(category: str | None) -> str:
    """Normalize a hazard category without inventing a critical class."""
    if category is None:
        return ""
    raw = str(category).strip().lower()
    if not raw:
        return ""
    return _CATEGORY_ALIASES.get(raw, raw)


def score_to_level(score: int) -> str:
    if score <= 4:
        return LEVEL_LOW
    if score <= 9:
        return LEVEL_MEDIUM
    if score <= 16:
        return LEVEL_HIGH
    return LEVEL_CRITICAL


def bump_level(level: str) -> str:
    index = RISK_LEVELS.index(level)
    return RISK_LEVELS[min(index + 1, len(RISK_LEVELS) - 1)]


def max_risk_level(current: str, minimum: str) -> str:
    return RISK_LEVELS[max(RISK_LEVELS.index(current), RISK_LEVELS.index(minimum))]


def _require_scale(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RiskInputError(f"{name} must be an integer from 1 to 5, not {type(value).__name__}")
    if value < 1 or value > 5:
        raise RiskInputError(f"{name} must be an integer from 1 to 5")
    return value


def _require_bool(name: str, value: Any) -> bool:
    if not isinstance(value, bool):
        raise RiskInputError(f"{name} must be a boolean")
    return value


def _require_people(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RiskInputError("people_exposed must be a non-negative integer")
    if value < 0:
        raise RiskInputError("people_exposed must not be negative")
    return value


def validate_risk_inputs(
    severity: Any,
    likelihood: Any,
    active: Any,
    people_exposed: Any,
    category: Any,
    already_injured: Any,
) -> tuple[int, int, bool, int, str, bool]:
    sev = _require_scale("severity", severity)
    like = _require_scale("likelihood", likelihood)
    is_active = _require_bool("active", active)
    people = _require_people(people_exposed)
    if category is not None and not isinstance(category, str):
        raise RiskInputError("category must be a string")
    injured = _require_bool("already_injured", already_injured)
    return sev, like, is_active, people, normalize_category(category), injured


def build_risk_explanation(
    *,
    severity: int,
    likelihood: int,
    score: int,
    base_level: str,
    final_level: str,
    category: str,
    people_exposed: int,
    injury_applied: bool,
    critical_applied: bool,
    exposure_applied: bool,
    exposure_changed: bool,
) -> str:
    parts = [f"Severity {severity} × likelihood {likelihood} = score {score} -> {base_level}."]
    if injury_applied:
        if exposure_changed:
            parts.append("Existing injury raises the minimum to High.")
        else:
            parts.append("Existing injury forces a minimum risk level of High.")
    if critical_applied:
        label = category or "critical-category"
        parts.append(f"Active {label} hazard forces the final level to {LEVEL_CRITICAL}.")
    if exposure_applied:
        if exposure_changed:
            parts.append(f"{people_exposed} people exposed bumps the level one step to {final_level}.")
        else:
            parts.append(
                f"{people_exposed} people are exposed; the risk is already at the maximum " f"{LEVEL_CRITICAL} level."
            )
    return " ".join(parts)


def calculate_risk(
    severity: int,
    likelihood: int,
    active: bool,
    people_exposed: int,
    category: str,
    already_injured: bool,
) -> dict:
    """Return the official risk classification.

    ``score`` is always ``severity * likelihood``. ``level`` may be raised by
    mandatory safety policy. The numeric score is never rewritten to match the
    policy-adjusted level.
    """
    sev, like, is_active, people, cat, injured = validate_risk_inputs(
        severity, likelihood, active, people_exposed, category, already_injured
    )
    score = sev * like
    base_level = score_to_level(score)
    level = base_level
    reasons: list[str] = []

    injury_applied = False
    if injured:
        level = max_risk_level(level, LEVEL_HIGH)
        injury_applied = True
        reasons.append(REASON_INJURY)

    critical_active = is_active and cat in CRITICAL_ACTIVE_CATEGORIES
    critical_applied = False
    if critical_active:
        level = max_risk_level(level, LEVEL_CRITICAL)
        critical_applied = True
        reasons.append(REASON_CRITICAL_ACTIVE)

    exposure_applied = people >= EXPOSURE_BUMP_THRESHOLD
    exposure_changed = False
    if exposure_applied:
        bumped = bump_level(level)
        exposure_changed = bumped != level
        level = bumped
        reasons.append(REASON_EXPOSURE)

    explanation = build_risk_explanation(
        severity=sev,
        likelihood=like,
        score=score,
        base_level=base_level,
        final_level=level,
        category=cat,
        people_exposed=people,
        injury_applied=injury_applied,
        critical_applied=critical_applied,
        exposure_applied=exposure_applied,
        exposure_changed=exposure_changed,
    )
    return {
        "score": score,
        "level": level,
        "explanation": explanation,
        "severity": sev,
        "likelihood": like,
        "base_level": base_level,
        "final_level": level,
        "escalation_applied": bool(reasons),
        "escalation_reasons": reasons,
        "factors": {
            "active": is_active,
            "people_exposed": people,
            "category": cat,
            "already_injured": injured,
        },
        "risk_policy_version": RISK_POLICY_VERSION,
    }
