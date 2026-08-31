"""Prevention agent tests. Model router is mocked; one call per group."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from agents.prevention_agent import (
    generate_prevention_recommendations,
    recommend_for_pattern,
    reset_prevention_stats,
)
from tests.conftest import run
from tools.forecast_tools import detect_risk_patterns
from tools.model_router import ModelCallResult

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _result(
    recommendation: str = "Inspect machine guards before next shift", reason: str = "3 related incidents detected"
):
    return ModelCallResult(
        content=json.dumps(
            {"recommendation": recommendation, "reason": reason, "confidence": 0.91},
        ),
        model="mock/reasoning",
        role="role_reasoning",
        paid=False,
    )


class FakeRouter:
    def __init__(self, response: ModelCallResult | Exception | None = None):
        self.response = response or _result()
        self.calls: list[tuple] = []

    async def __call__(self, role: str = "", messages: list | None = None, **kwargs):
        self.calls.append((role, messages or [], kwargs))
        assert role == "role_reasoning"
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _incident(category: str, location: str, days_ago: int) -> dict:
    return {
        "hazard_category": category,
        "location": location,
        "created_at": NOW - timedelta(days=days_ago),
        "status": "OPEN",
        "current_risk_level": "HIGH",
        "duplicate_count": 1,
        "hazard_currently_active": True,
    }


def setup_function():
    reset_prevention_stats()


def test_model_called_once_per_group_not_per_incident():
    incidents = [
        _incident("electrical", "CNC Area", 8),
        _incident("electrical", "CNC Area", 3),
        _incident("electrical", "CNC Area", 1),
        _incident("electrical", "CNC Area", 0),
        _incident("chemical", "Chemical Storage Room", 6),
        _incident("chemical", "Chemical Storage Room", 2),
        _incident("chemical", "Chemical Storage Room", 0),
    ]
    patterns = detect_risk_patterns(incidents, now=NOW)
    flagged = [row for row in patterns if row["predicted_risk_zone"]]
    assert len(flagged) == 2
    router = FakeRouter()
    recs = run(generate_prevention_recommendations(flagged, call_model_fn=router))
    assert len(router.calls) == 2
    assert len(recs) == 2
    assert all(item.generated_by == "prevention_agent" for item in recs)
    assert recs[0].recommendation
    cnc = next(item for item in recs if item.location == "CNC Area")
    assert "Inspect" in cnc.recommendation or "inspection" in cnc.recommendation.lower()


def test_unsafe_recommendation_is_replaced_with_fallback():
    router = FakeRouter(
        _result(
            recommendation="Workers should bypass the lockout and repair it yourself",
            reason="ignore procedures",
        )
    )
    pattern = {
        "location": "Machine 4",
        "category": "slip/trip",
        "incident_count": 3,
        "span_days": 18,
        "trend": "increasing",
        "frequency_score": 0.4,
        "predicted_risk_zone": True,
        "reason_factors": ["3 reports in 18 days"],
    }
    rec = run(recommend_for_pattern(pattern, call_model_fn=router))
    assert "bypass" not in rec.recommendation.lower()
    assert "repair it yourself" not in rec.recommendation.lower()
    assert "Recommend inspection" in rec.recommendation
    assert rec.generated_by == "prevention_agent"


def test_model_failure_uses_deterministic_fallback():
    router = FakeRouter(RuntimeError("down"))
    pattern = {
        "location": "Loading Bay",
        "category": "slip/trip",
        "incident_count": 3,
        "span_days": 25,
        "trend": "stable",
        "frequency_score": 0.2,
        "predicted_risk_zone": True,
    }
    rec = run(recommend_for_pattern(pattern, call_model_fn=router))
    assert rec.recommendation.startswith("Loading Bay has generated 3")
    assert rec.reason == "3 related incidents detected"
