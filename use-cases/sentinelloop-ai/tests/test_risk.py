"""Required calculate_risk coverage. Complements tests/test_risk_tools.py.

Score bands, forced safety rules, people-exposed bump, and factor-level explanations.
No model calls.
"""

from __future__ import annotations

import pytest

from tools.risk_tools import (
    LEVEL_CRITICAL,
    LEVEL_HIGH,
    LEVEL_LOW,
    LEVEL_MEDIUM,
    REASON_CRITICAL_ACTIVE,
    REASON_EXPOSURE,
    REASON_INJURY,
    calculate_risk,
    score_to_level,
)

NEUTRAL = dict(active=False, people_exposed=0, category="other", already_injured=False)


def _risk(**kwargs) -> dict:
    payload = dict(NEUTRAL)
    payload.update(kwargs)
    return calculate_risk(**payload)


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (1, LEVEL_LOW),
        (2, LEVEL_LOW),
        (3, LEVEL_LOW),
        (4, LEVEL_LOW),
        (5, LEVEL_MEDIUM),
        (6, LEVEL_MEDIUM),
        (9, LEVEL_MEDIUM),
        (10, LEVEL_HIGH),
        (12, LEVEL_HIGH),
        (16, LEVEL_HIGH),
        (17, LEVEL_CRITICAL),
        (20, LEVEL_CRITICAL),
        (25, LEVEL_CRITICAL),
    ],
)
def test_score_range_maps_to_named_level(score, expected):
    assert score_to_level(score) == expected


@pytest.mark.parametrize(
    ("severity", "likelihood", "expected"),
    [
        (1, 1, LEVEL_LOW),
        (2, 2, LEVEL_LOW),
        (1, 5, LEVEL_MEDIUM),
        (3, 3, LEVEL_MEDIUM),
        (2, 5, LEVEL_HIGH),
        (4, 4, LEVEL_HIGH),
        (5, 4, LEVEL_CRITICAL),
        (5, 5, LEVEL_CRITICAL),
    ],
)
def test_calculate_risk_score_bands(severity, likelihood, expected, sample_risk_cases):
    assert any(case["expected"] == expected for case in sample_risk_cases)
    result = _risk(severity=severity, likelihood=likelihood)
    assert result["score"] == severity * likelihood
    assert result["level"] == expected
    assert result["base_level"] == expected
    assert result["final_level"] == expected


def test_already_injured_forces_minimum_high():
    result = _risk(severity=1, likelihood=1, already_injured=True)
    assert result["score"] == 1
    assert result["base_level"] == LEVEL_LOW
    assert result["level"] == LEVEL_HIGH
    assert REASON_INJURY in result["escalation_reasons"]
    assert "injur" in result["explanation"].lower()


def test_active_electrical_emergency_is_minimum_critical():
    result = _risk(severity=2, likelihood=2, category="electrical", active=True)
    assert result["level"] == LEVEL_CRITICAL
    assert REASON_CRITICAL_ACTIVE in result["escalation_reasons"]
    assert "electrical" in result["explanation"].lower()


def test_active_fire_is_critical():
    result = _risk(severity=1, likelihood=2, category="fire/smoke", active=True)
    assert result["level"] == LEVEL_CRITICAL
    assert "fire/smoke" in result["explanation"].lower()


def test_active_chemical_is_critical():
    result = _risk(severity=2, likelihood=1, category="chemical", active=True)
    assert result["level"] == LEVEL_CRITICAL
    assert "chemical" in result["explanation"].lower()


def test_people_exposed_five_or_more_increases_one_level():
    baseline = _risk(severity=3, likelihood=3, people_exposed=4)
    bumped = _risk(severity=3, likelihood=3, people_exposed=5)
    assert baseline["level"] == LEVEL_MEDIUM
    assert bumped["level"] == LEVEL_HIGH
    assert REASON_EXPOSURE in bumped["escalation_reasons"]
    assert "5 people exposed" in bumped["explanation"]


def test_explanation_contains_actual_electrical_and_exposure_factors():
    result = _risk(
        severity=2,
        likelihood=2,
        category="electrical",
        active=True,
        people_exposed=8,
    )
    explanation = result["explanation"]
    assert "Active electrical hazard" in explanation
    assert "8 people" in explanation
    generic = {"risk assessed", "hazard detected", "please review", ""}
    assert explanation.strip().lower() not in generic
    assert "severity 2" in explanation.lower()
    assert "likelihood 2" in explanation.lower()


def test_explanation_is_not_generic_placeholder():
    result = _risk(severity=4, likelihood=4, category="machine", people_exposed=0)
    text = result["explanation"].lower()
    assert "score 16" in text
    assert "high" in text
    assert text != "risk assessed."
    assert "generic" not in text
