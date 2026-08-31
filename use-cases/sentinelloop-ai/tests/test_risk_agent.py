"""Unit tests for SentinelLoop risk_agent. Model calls are mocked."""

from __future__ import annotations

import asyncio
import json

import pytest
from agentkernel.core.base import Session

from agents.risk_agent import (
    ASSESSMENT_FALLBACK,
    ASSESSMENT_MODEL,
    RiskAssessment,
    assess_risk,
    build_fallback_estimate,
)
from tools.model_router import ModelCallResult
from tools.risk_tools import LEVEL_CRITICAL, LEVEL_HIGH, LEVEL_LOW, LEVEL_MEDIUM


def run(coro):
    return asyncio.run(coro)


def _estimate(**kwargs) -> dict:
    base = {
        "severity": 3,
        "likelihood": 3,
        "severity_reason": "A fall could cause a meaningful worker injury.",
        "likelihood_reason": "Workers are currently walking through the contaminated area.",
        "severity_confidence": 0.84,
        "likelihood_confidence": 0.94,
    }
    base.update(kwargs)
    return base


def _result(data: dict | None = None, **kwargs) -> ModelCallResult:
    payload = _estimate(**(data or {}))
    return ModelCallResult(
        content=kwargs.pop("content", json.dumps(payload)),
        model="mock/reasoning",
        role="role_reasoning",
        degraded=kwargs.pop("degraded", False),
        error=kwargs.pop("error", None),
        paid=False,
    )


class FakeRouter:
    def __init__(self, response: ModelCallResult | Exception) -> None:
        self.response = response
        self.calls: list[tuple] = []

    async def __call__(self, role: str = "", messages: list | None = None, **kwargs):
        self.calls.append((role, messages or [], kwargs))
        assert role == "role_reasoning"
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _assess(incident: dict, router: FakeRouter, session: Session | None = None) -> RiskAssessment:
    return run(assess_risk(incident, call_model_fn=router, session=session))


def test_valid_model_estimate_oil_spill():
    router = FakeRouter(_result({"severity": 3, "likelihood": 4}))
    result = _assess(
        {
            "translated_text": "Oil is covering the floor near the loading bay and workers are walking through it.",
            "hazard_category": "slip/trip",
            "location": "loading bay",
            "people_exposed": 3,
            "is_active": True,
            "already_injured": False,
        },
        router,
    )
    assert result.severity == 3
    assert result.likelihood == 4
    assert result.score == 12
    assert result.base_level == LEVEL_HIGH
    assert result.level == LEVEL_HIGH
    assert result.reviewed_by_human is False
    assert result.requires_human_review is True
    assert result.review_status == "pending"
    assert result.assessment_source == ASSESSMENT_MODEL
    assert router.calls[0][0] == "role_reasoning"


@pytest.mark.parametrize("severity", [1, 5])
@pytest.mark.parametrize("likelihood", [1, 5])
def test_severity_and_likelihood_extremes(severity, likelihood):
    router = FakeRouter(_result({"severity": severity, "likelihood": likelihood}))
    result = _assess({"hazard_category": "other", "is_active": False, "already_injured": False}, router)
    assert result.severity == severity
    assert result.likelihood == likelihood
    assert result.score == severity * likelihood


def test_model_provided_risk_level_is_ignored_for_active_electrical():
    router = FakeRouter(
        _result(
            {
                "severity": 2,
                "likelihood": 2,
                "risk_level": "Low",
                "severity_reason": "Contact with the exposed electrical conductor could cause serious injury.",
                "likelihood_reason": "The cable remains exposed in an occupied work area.",
            }
        )
    )
    result = _assess(
        {
            "translated_text": "The electrical panel is still sparking.",
            "hazard_category": "electrical",
            "is_active": True,
            "already_injured": False,
        },
        router,
    )
    assert result.severity == 2
    assert result.likelihood == 2
    assert result.score == 4
    assert result.base_level == LEVEL_LOW
    assert result.level == LEVEL_CRITICAL
    assert result.requires_human_review is True
    assert result.reviewed_by_human is False


def test_active_fire_override():
    router = FakeRouter(_result({"severity": 4, "likelihood": 3}))
    result = _assess(
        {
            "translated_text": "Smoke and flames are coming from the generator now.",
            "hazard_category": "fire/smoke",
            "people_exposed": 2,
            "is_active": True,
            "already_injured": False,
        },
        router,
    )
    assert result.score == 12
    assert result.base_level == LEVEL_HIGH
    assert result.level == LEVEL_CRITICAL


def test_invalid_json_uses_fallback():
    router = FakeRouter(_result(content="not-json"))
    result = _assess({"hazard_category": "slip/trip", "is_active": True}, router)
    assert result.assessment_source == ASSESSMENT_FALLBACK
    assert result.severity_confidence <= 0.4
    assert 1 <= result.severity <= 5


def test_missing_severity_uses_fallback():
    router = FakeRouter(_result(content=json.dumps({"likelihood": 3})))
    result = _assess({"hazard_category": "machine", "is_active": False}, router)
    assert result.assessment_source == ASSESSMENT_FALLBACK


def test_missing_likelihood_uses_fallback():
    router = FakeRouter(_result(content=json.dumps({"severity": 3})))
    result = _assess({"hazard_category": "machine", "is_active": False}, router)
    assert result.assessment_source == ASSESSMENT_FALLBACK


def test_out_of_range_model_values_use_fallback():
    router = FakeRouter(_result({"severity": 999, "likelihood": -2}))
    result = _assess({"hazard_category": "electrical", "is_active": True}, router)
    assert result.assessment_source == ASSESSMENT_FALLBACK
    assert result.level == LEVEL_CRITICAL


def test_model_exception_fallback_keeps_emergency_critical():
    router = FakeRouter(TimeoutError("timeout"))
    result = _assess(
        {
            "translated_text": "The electrical panel is still sparking.",
            "hazard_category": "electrical",
            "is_active": True,
            "already_injured": False,
        },
        router,
    )
    assert result.assessment_source == ASSESSMENT_FALLBACK
    assert result.level == LEVEL_CRITICAL
    assert result.reviewed_by_human is False


def test_none_people_exposed_does_not_invent_count():
    router = FakeRouter(_result({"severity": 3, "likelihood": 3}))
    result = _assess(
        {"hazard_category": "slip/trip", "is_active": True, "people_exposed": None, "already_injured": False},
        router,
    )
    assert result.people_exposed_known is False
    assert "unknown_exposure_count" in result.risk_factors
    assert result.level == LEVEL_MEDIUM


@pytest.mark.parametrize(
    ("level_incident", "sev", "like", "requires"),
    [
        ({"hazard_category": "other", "is_active": False}, 1, 1, False),
        ({"hazard_category": "slip/trip", "is_active": True, "people_exposed": 1}, 3, 2, False),
        ({"hazard_category": "machine", "is_active": True, "people_exposed": 2}, 4, 3, True),
        ({"hazard_category": "electrical", "is_active": True}, 2, 2, True),
    ],
)
def test_human_review_flags(level_incident, sev, like, requires):
    router = FakeRouter(_result({"severity": sev, "likelihood": like}))
    result = _assess({**level_incident, "already_injured": False}, router)
    assert result.requires_human_review is requires
    assert result.reviewed_by_human is False
    if requires:
        assert result.review_status == "pending"
        assert result.level in {LEVEL_HIGH, LEVEL_CRITICAL}
    else:
        assert result.review_status == "not_required"
        assert result.level in {LEVEL_LOW, LEVEL_MEDIUM}


def test_preserves_incident_identifiers():
    router = FakeRouter(_result({"severity": 2, "likelihood": 2}))
    result = _assess(
        {
            "hazard_category": "other",
            "is_active": False,
            "already_injured": False,
            "incident_id": "inc-9",
            "session_id": "+94770000000",
            "worker_phone": "+94770000000",
            "translated_text": "A light is flickering.",
        },
        router,
    )
    assert result.incident_id == "inc-9"
    assert result.session_id == "+94770000000"
    assert result.incident["translated_text"] == "A light is flickering."


def test_session_cache_round_trip():
    session = Session("sess-risk")
    router = FakeRouter(_result({"severity": 3, "likelihood": 3}))
    result = _assess({"hazard_category": "other", "is_active": False, "session_id": "sess-risk"}, router, session)
    cached = session.get_non_volatile_cache().get("last_risk_assessment")
    assert cached["score"] == result.score
    assert cached["reviewed_by_human"] is False


def test_idempotent_with_same_model_output():
    incident = {"hazard_category": "machine", "is_active": False, "already_injured": False}
    first = _assess(incident, FakeRouter(_result({"severity": 3, "likelihood": 2})))
    second = _assess(incident, FakeRouter(_result({"severity": 3, "likelihood": 2})))
    assert first.score == second.score
    assert first.level == second.level
    assert first.explanation == second.explanation


def test_fallback_active_electrical_is_still_critical():
    estimate = build_fallback_estimate({"hazard_category": "electrical", "is_active": True})
    result = run(
        assess_risk(
            {"hazard_category": "electrical", "is_active": True},
            call_model_fn=FakeRouter(RuntimeError("down")),
        )
    )
    assert estimate.severity_confidence == 0.35
    assert result.level == LEVEL_CRITICAL
    assert result.assessment_source == ASSESSMENT_FALLBACK


def test_does_not_set_assessment_source_human():
    router = FakeRouter(_result({"severity": 5, "likelihood": 5}))
    result = _assess({"hazard_category": "structural", "is_active": True}, router)
    assert result.assessment_source != "human"
    assert result.human_level is None
