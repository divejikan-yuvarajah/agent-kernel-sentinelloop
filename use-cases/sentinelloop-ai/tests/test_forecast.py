"""Deterministic forecast_tools tests. No LLM, Slack, or live database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tools.forecast_tools import (
    DEFAULT_FREQUENCY_THRESHOLD,
    detect_risk_patterns,
    detect_trend,
    frequency_score_for,
    frequency_threshold,
    reset_forecast_stats,
)

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _incident(*, category: str, location: str, days_ago: int, **extra):
    created = NOW - timedelta(days=days_ago)
    row = {
        "hazard_category": category,
        "location": location,
        "created_at": created,
        "status": extra.pop("status", "OPEN"),
        "current_risk_level": extra.pop("current_risk_level", "HIGH"),
        "duplicate_count": extra.pop("duplicate_count", 1),
        "hazard_currently_active": extra.pop("hazard_currently_active", True),
    }
    row.update(extra)
    return row


def setup_function():
    reset_forecast_stats()


def test_same_category_location_creates_one_pattern():
    incidents = [
        _incident(category="electrical", location="CNC Area", days_ago=2),
        _incident(category="Electrical", location="CNC Area", days_ago=1),
        _incident(category="electrical", location="CNC Area", days_ago=0),
    ]
    patterns = detect_risk_patterns(incidents, now=NOW)
    assert len(patterns) == 1
    assert patterns[0]["incident_count"] == 3
    assert patterns[0]["location"].lower() == "cnc area"


def test_different_locations_create_separate_patterns():
    incidents = [
        _incident(category="slip/trip", location="Loading Bay", days_ago=3),
        _incident(category="slip/trip", location="Loading Bay", days_ago=1),
        _incident(category="slip/trip", location="Main Workshop Floor", days_ago=2),
        _incident(category="slip/trip", location="Main Workshop Floor", days_ago=0),
    ]
    patterns = detect_risk_patterns(incidents, now=NOW)
    locations = {item["location"] for item in patterns}
    assert len(patterns) == 2
    assert "Loading Bay" in locations
    assert "Main Workshop Floor" in locations


def test_less_than_two_incidents_does_not_predict():
    incidents = [_incident(category="chemical", location="Chemical Storage Room", days_ago=1)]
    patterns = detect_risk_patterns(incidents, now=NOW)
    assert patterns == []


def test_closed_incidents_are_included():
    incidents = [
        _incident(category="chemical", location="Chemical Storage", days_ago=4, status="CLOSED"),
        _incident(category="chemical", location="Chemical Storage", days_ago=1, status="OPEN"),
    ]
    patterns = detect_risk_patterns(incidents, now=NOW)
    assert len(patterns) == 1
    assert patterns[0]["incident_count"] == 2


def test_frequency_score_is_deterministic():
    stamps = [NOW - timedelta(days=days) for days in (0, 4, 9)]
    first = frequency_score_for(stamps, NOW)
    second = frequency_score_for(stamps, NOW)
    expected = round(1 / 1 + 1 / 5 + 1 / 10, 6)
    assert first == second == expected


def test_trend_increasing_when_latest_gap_is_shorter():
    stamps = [
        NOW - timedelta(days=17),
        NOW - timedelta(days=7),
        NOW - timedelta(days=2),
        NOW,
    ]
    assert detect_trend(stamps) == "increasing"
    incidents = [_incident(category="electrical", location="CNC Area", days_ago=days) for days in (17, 7, 2, 0)]
    pattern = detect_risk_patterns(incidents, now=NOW)[0]
    assert pattern["trend"] == "increasing"


def test_trend_stable_when_latest_gap_is_not_shorter():
    stamps = [
        NOW - timedelta(days=17),
        NOW - timedelta(days=15),
        NOW - timedelta(days=10),
        NOW,
    ]
    assert detect_trend(stamps) == "stable"


def test_threshold_comes_from_environment(monkeypatch):
    monkeypatch.delenv("PREDICTION_FREQUENCY_THRESHOLD", raising=False)
    assert frequency_threshold() == DEFAULT_FREQUENCY_THRESHOLD
    monkeypatch.setenv("PREDICTION_FREQUENCY_THRESHOLD", "0.5")
    assert frequency_threshold() == 0.5
    incidents = [
        _incident(category="ppe", location="Welding Section", days_ago=20),
        _incident(category="ppe", location="Welding Section", days_ago=19),
    ]
    low = detect_risk_patterns(incidents, now=NOW, threshold=0.01)
    high = detect_risk_patterns(incidents, now=NOW, threshold=9.0)
    assert low[0]["predicted_risk_zone"] is True
    assert high[0]["predicted_risk_zone"] is False


def test_location_hotspot_multiple_categories():
    incidents = [
        _incident(category="electrical", location="CNC Area", days_ago=3),
        _incident(category="electrical", location="CNC Area", days_ago=1),
        _incident(category="machine", location="CNC Area", days_ago=2),
        _incident(category="ppe", location="CNC Area", days_ago=0),
    ]
    patterns = detect_risk_patterns(incidents, now=NOW)
    electrical = next(item for item in patterns if item["category_key"] == "electrical")
    assert electrical["location_hotspot"] is True
    assert "multiple hazard categories at this location" in electrical["reason_factors"]
