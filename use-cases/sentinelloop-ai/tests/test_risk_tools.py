"""Deterministic tests for the SentinelLoop risk engine. No model calls."""

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
    RiskInputError,
    bump_level,
    calculate_risk,
    normalize_category,
    score_to_level,
)

NEUTRAL = dict(active=False, people_exposed=0, category="other", already_injured=False)


def _risk(**kwargs) -> dict:
    payload = dict(NEUTRAL)
    payload.update(kwargs)
    return calculate_risk(**payload)


@pytest.mark.parametrize(
    ("severity", "likelihood", "expected_level"),
    [
        (1, 1, LEVEL_LOW),
        (1, 4, LEVEL_LOW),
        (1, 5, LEVEL_MEDIUM),
        (3, 3, LEVEL_MEDIUM),
        (2, 5, LEVEL_HIGH),
        (4, 4, LEVEL_HIGH),
        (5, 4, LEVEL_CRITICAL),
        (5, 5, LEVEL_CRITICAL),
    ],
)
def test_matrix_boundaries(severity, likelihood, expected_level):
    result = _risk(severity=severity, likelihood=likelihood)
    score = severity * likelihood
    assert result["score"] == score
    assert result["base_level"] == expected_level
    assert result["level"] == expected_level
    assert result["final_level"] == expected_level


def test_score_to_level_edges():
    assert score_to_level(1) == LEVEL_LOW
    assert score_to_level(4) == LEVEL_LOW
    assert score_to_level(5) == LEVEL_MEDIUM
    assert score_to_level(9) == LEVEL_MEDIUM
    assert score_to_level(10) == LEVEL_HIGH
    assert score_to_level(16) == LEVEL_HIGH
    assert score_to_level(17) == LEVEL_CRITICAL
    assert score_to_level(25) == LEVEL_CRITICAL


@pytest.mark.parametrize("severity", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("likelihood", [1, 2, 3, 4, 5])
def test_all_severity_likelihood_combinations(severity, likelihood):
    result = _risk(severity=severity, likelihood=likelihood)
    score = severity * likelihood
    assert result["score"] == score
    assert result["level"] == score_to_level(score)
    assert result["base_level"] == result["level"]
    assert result["escalation_applied"] is False


@pytest.mark.parametrize(
    ("severity", "likelihood", "expected"),
    [
        (1, 1, LEVEL_HIGH),
        (3, 2, LEVEL_HIGH),
        (4, 3, LEVEL_HIGH),
        (5, 5, LEVEL_CRITICAL),
    ],
)
def test_already_injured_minimum_high(severity, likelihood, expected):
    result = _risk(severity=severity, likelihood=likelihood, already_injured=True)
    assert result["score"] == severity * likelihood
    assert result["level"] == expected
    assert REASON_INJURY in result["escalation_reasons"]
    assert "injur" in result["explanation"].lower()


def test_case_a_low_plus_injury_is_high():
    result = _risk(severity=2, likelihood=2, already_injured=True)
    assert result["score"] == 4
    assert result["base_level"] == LEVEL_LOW
    assert result["level"] == LEVEL_HIGH


def test_case_b_injury_then_exposure_is_critical():
    result = _risk(severity=2, likelihood=2, people_exposed=7, already_injured=True, category="machine")
    assert result["score"] == 4
    assert result["base_level"] == LEVEL_LOW
    assert result["level"] == LEVEL_CRITICAL
    assert result["escalation_reasons"] == [REASON_INJURY, REASON_EXPOSURE]


@pytest.mark.parametrize("category", ["electrical", "fire/smoke", "chemical"])
def test_active_critical_categories_are_critical(category):
    result = _risk(severity=2, likelihood=2, active=True, category=category)
    assert result["score"] == 4
    assert result["base_level"] == LEVEL_LOW
    assert result["level"] == LEVEL_CRITICAL
    assert REASON_CRITICAL_ACTIVE in result["escalation_reasons"]


@pytest.mark.parametrize("category", ["electrical", "fire/smoke", "chemical"])
def test_inactive_critical_categories_follow_matrix(category):
    result = _risk(severity=2, likelihood=2, active=False, category=category)
    assert result["level"] == LEVEL_LOW
    assert REASON_CRITICAL_ACTIVE not in result["escalation_reasons"]


def test_case_c_active_electrical_low_score_is_critical():
    result = _risk(severity=2, likelihood=2, active=True, category="electrical")
    assert result["level"] == LEVEL_CRITICAL
    assert result["score"] == 4


def test_case_d_critical_plus_exposure_stays_critical():
    result = _risk(severity=5, likelihood=5, people_exposed=10, category="machine")
    assert result["score"] == 25
    assert result["base_level"] == LEVEL_CRITICAL
    assert result["level"] == LEVEL_CRITICAL
    assert bump_level(LEVEL_CRITICAL) == LEVEL_CRITICAL


def test_case_e_active_chemical_and_exposure_is_critical():
    result = _risk(severity=4, likelihood=3, active=True, people_exposed=20, category="chemical")
    assert result["score"] == 12
    assert result["base_level"] == LEVEL_HIGH
    assert result["level"] == LEVEL_CRITICAL


@pytest.mark.parametrize("people", [0, 1, 4])
def test_exposure_below_threshold_does_not_bump(people):
    result = _risk(severity=3, likelihood=3, people_exposed=people)
    assert result["level"] == LEVEL_MEDIUM
    assert REASON_EXPOSURE not in result["escalation_reasons"]


@pytest.mark.parametrize("people", [5, 6, 100])
def test_exposure_at_or_above_threshold_bumps(people):
    result = _risk(severity=3, likelihood=3, people_exposed=people)
    assert result["score"] == 9
    assert result["base_level"] == LEVEL_MEDIUM
    assert result["level"] == LEVEL_HIGH
    assert REASON_EXPOSURE in result["escalation_reasons"]
    assert str(people) in result["explanation"]


def test_example_electrical_active_and_eight_people():
    result = calculate_risk(
        severity=3,
        likelihood=3,
        active=True,
        people_exposed=8,
        category="electrical",
        already_injured=False,
    )
    assert result["score"] == 9
    assert result["base_level"] == LEVEL_MEDIUM
    assert result["level"] == LEVEL_CRITICAL
    assert result["escalation_applied"] is True
    assert result["escalation_reasons"] == [REASON_CRITICAL_ACTIVE, REASON_EXPOSURE]
    assert "8" in result["explanation"]
    assert "electrical" in result["explanation"].lower()


def test_example_injury_and_exposure():
    result = calculate_risk(2, 2, False, 6, "machine", True)
    assert result["score"] == 4
    assert result["base_level"] == LEVEL_LOW
    assert result["level"] == LEVEL_CRITICAL


def test_example_normal_medium():
    result = calculate_risk(3, 2, True, 2, "slip/trip", False)
    assert result["score"] == 6
    assert result["base_level"] == LEVEL_MEDIUM
    assert result["level"] == LEVEL_MEDIUM
    assert result["escalation_applied"] is False


def test_score_not_rewritten_when_level_escalates():
    result = _risk(severity=2, likelihood=2, active=True, category="electrical")
    assert result["score"] == 4
    assert result["level"] == LEVEL_CRITICAL


def test_combined_overrides_never_lower_risk():
    result = _risk(
        severity=2,
        likelihood=2,
        active=True,
        people_exposed=8,
        category="electrical",
        already_injured=True,
    )
    assert result["level"] == LEVEL_CRITICAL
    assert result["score"] == 4
    assert REASON_INJURY in result["escalation_reasons"]
    assert REASON_CRITICAL_ACTIVE in result["escalation_reasons"]
    assert REASON_EXPOSURE in result["escalation_reasons"]


def test_category_normalization():
    assert normalize_category("Electrical") == "electrical"
    assert normalize_category(" electrical ") == "electrical"
    assert normalize_category("FIRE/SMOKE") == "fire/smoke"
    assert normalize_category("Chemical") == "chemical"
    assert normalize_category("laser") == "laser"
    result = _risk(severity=2, likelihood=2, active=True, category=" Electrical ")
    assert result["level"] == LEVEL_CRITICAL


def test_unknown_category_is_not_forced_critical():
    result = _risk(severity=2, likelihood=2, active=True, category="unknown gadget")
    assert result["level"] == LEVEL_LOW


@pytest.mark.parametrize(
    "kwargs",
    [
        {"severity": 0},
        {"severity": 6},
        {"severity": -1},
        {"likelihood": 0},
        {"likelihood": 10},
        {"people_exposed": -1},
        {"severity": True},
        {"likelihood": False},
    ],
)
def test_invalid_inputs_rejected(kwargs):
    payload = dict(severity=3, likelihood=3)
    payload.update(kwargs)
    with pytest.raises(RiskInputError):
        _risk(**payload)


def test_empty_category_is_allowed():
    result = _risk(severity=3, likelihood=3, category="")
    assert result["level"] == LEVEL_MEDIUM
    assert result["factors"]["category"] == ""


def test_idempotent_classification():
    first = _risk(severity=4, likelihood=4, active=True, people_exposed=5, category="fire/smoke")
    second = _risk(severity=4, likelihood=4, active=True, people_exposed=5, category="fire/smoke")
    assert first == second
