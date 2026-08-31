"""Unit tests for SentinelLoop incident extraction. Model calls are mocked."""

from __future__ import annotations

import asyncio
import json

import pytest
from agentkernel.core.base import Session

from agents.incident_agent import (
    IncidentAnalysis,
    analyze_incident,
    generate_clarification_question,
    normalize_hazard_category,
    normalize_people_exposed,
)
from agents.intake_agent import IntakeResult
from tools.model_router import ModelCallResult


def run(coro):
    return asyncio.run(coro)


def _payload(**kwargs) -> dict:
    base = {
        "hazard_category": "electrical",
        "location": None,
        "equipment_involved": None,
        "people_exposed": None,
        "is_active": True,
        "already_injured": False,
        "secondary_hazards": [],
        "emergency_type": None,
        "emergency_reason": None,
        "emergency_confidence": 0.0,
        "risk_indicators": [],
        "injury_summary": None,
        "exposure_type": None,
        "equipment_state": None,
        "worker_reports_urgent": False,
        "severity": "medium",
        "classification_reason": "Supported by the worker report.",
        "confidence": {
            "hazard_category": 0.9,
            "location": 0.2,
            "equipment_involved": 0.2,
            "people_exposed": 0.1,
            "is_active": 0.8,
            "already_injured": 0.9,
        },
        "evidence": {},
    }
    base.update(kwargs)
    return base


def _result(data: dict | None = None, **kwargs) -> ModelCallResult:
    payload = _payload(**(data or {}))
    return ModelCallResult(
        content=kwargs.pop("content", json.dumps(payload)),
        model="mock/free",
        role="role_fast",
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
        assert role == "role_fast"
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _analyze(text: str, router: FakeRouter, **extra) -> IncidentAnalysis:
    draft = {"translated_text": text, "raw_text": extra.pop("raw_text", text), **extra}
    return run(analyze_incident(draft, call_model_fn=router))


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("exposed live cable sparking", "electrical"),
        ("smoke coming from the motor", "fire/smoke"),
        ("acid leaking from a drum", "chemical"),
        ("unguarded lathe still running", "machine"),
        ("oil spilled all over the floor", "slip/trip"),
        ("welding without safety glasses", "missing PPE"),
        ("scaffold is leaning and unstable", "structural"),
        ("worker climbing over a moving conveyor", "unsafe behaviour"),
        ("strange buzzing noise in the office", "other"),
    ],
)
def test_hazard_categories(text, category):
    router = FakeRouter(_result({"hazard_category": category, "location": "Bay 1", "is_active": True}))
    result = _analyze(text, router)
    assert result.hazard_category == category
    assert router.calls[0][0] == "role_fast"


def test_unsupported_category_becomes_other():
    router = FakeRouter(_result({"hazard_category": "laser-beam", "location": "Lab", "is_active": True}))
    assert _analyze("weird laser", router).hazard_category == "other"


def test_qr_location_overrides_and_skips_location_question():
    router = FakeRouter(
        _result(
            {
                "hazard_category": "electrical",
                "location": "somewhere vague",
                "equipment_involved": "unknown box",
                "is_active": True,
                "emergency_type": "electrical",
                "severity": "critical",
                "risk_indicators": ["electrical sparking"],
            }
        )
    )
    result = run(
        analyze_incident(
            {
                "raw_text": "Panel eka spark wenawa danuth",
                "translated_text": "The panel is still sparking.",
                "language": "si",
                "qr_location": "Factory A / Electrical Room",
                "qr_equipment": "Panel B17",
                "message_type": "image",
            },
            call_model_fn=router,
        )
    )
    assert result.location == "Factory A / Electrical Room"
    assert result.equipment_involved == "Panel B17"
    assert result.qr_location == "Factory A / Electrical Room"
    assert result.qr_equipment == "Panel B17"
    assert result.has_image is True
    assert result.needs_clarification is False
    assert result.skip_clarification is True
    assert result.recommended_action == "immediate_escalation"
    assert result.confidence.location == 1.0
    assert result.confidence.equipment_involved == 1.0
    assert result.source == "QR_TAGGED"
    assert result.location_confidence == 1.0


def test_qr_prevents_location_clarification_on_non_emergency():
    router = FakeRouter(_result({"hazard_category": "slip/trip", "location": None, "is_active": True}))
    result = run(
        analyze_incident(
            {"translated_text": "Oil is spilled all over the floor.", "qr_location": "Packing area"},
            call_model_fn=router,
        )
    )
    assert result.location == "Packing area"
    assert result.clarification_question != "Where is this hazard?"
    assert result.needs_clarification is False or result.clarification_history[-1:] != ["location"]


def test_missing_location_asks_only_location():
    router = FakeRouter(_result({"hazard_category": "slip/trip", "location": None, "is_active": True}))
    result = _analyze("Oil is spilled all over the floor and people are walking there.", router)
    assert result.needs_clarification is True
    assert result.clarification_question == "Where is this hazard?"
    assert result.skip_clarification is False


def test_missing_category_asks_category():
    router = FakeRouter(_result({"hazard_category": None, "location": "Warehouse 2", "is_active": True}))
    result = _analyze("Something dangerous in Warehouse 2", router)
    assert result.clarification_question == "What hazard did you notice?"


def test_missing_active_asks_active():
    router = FakeRouter(_result({"hazard_category": "chemical", "location": "Store", "is_active": None}))
    result = _analyze("There was a chemical smell in the store", router)
    assert result.clarification_question == "Is the hazard still happening now?"


def test_multiple_missing_asks_one_question():
    router = FakeRouter(_result({"hazard_category": None, "location": None, "is_active": None}))
    result = _analyze("problem near a machine", router)
    assert result.needs_clarification is True
    assert result.clarification_question == "Where is this hazard?"
    assert result.clarification_question.count("?") == 1


@pytest.mark.parametrize(
    "text",
    [
        "Fire is spreading near the generator.",
        "There is heavy smoke coming from the machine.",
        "Gas is leaking and workers are still inside.",
        "A live cable is on the floor.",
        "Acid is leaking from a tank.",
    ],
)
def test_emergencies_skip_clarification(text):
    router = FakeRouter(_result({"hazard_category": "other", "location": None, "is_active": True}))
    result = _analyze(text, router)
    assert result.skip_clarification is True
    assert result.needs_clarification is False
    assert result.recommended_action == "immediate_escalation"
    assert result.is_active is True


def test_negation_no_fire():
    router = FakeRouter(_result({"hazard_category": "fire/smoke", "location": "Bay", "is_active": False}))
    result = _analyze("No fire now.", router)
    assert result.skip_clarification is False
    assert result.is_active is False


def test_nobody_injured():
    router = FakeRouter(
        _result({"hazard_category": "slip/trip", "location": "Hall", "is_active": True, "already_injured": False})
    )
    result = _analyze("Nobody has been injured.", router)
    assert result.already_injured is False


def test_leak_stopped_not_active():
    router = FakeRouter(_result({"hazard_category": "chemical", "location": "Plant", "is_active": False}))
    result = _analyze("The chemical leak was stopped.", router)
    assert result.is_active is False
    assert result.skip_clarification is False


def test_not_sparking_now():
    router = FakeRouter(_result({"hazard_category": "electrical", "location": "Room", "is_active": False}))
    result = _analyze("The wire is not sparking now.", router)
    assert result.is_active is False


def test_historical_fire():
    router = FakeRouter(
        _result({"hazard_category": "fire/smoke", "location": "Shop", "is_active": False, "severity": "medium"})
    )
    result = _analyze("The motor caught fire yesterday but maintenance repaired it.", router)
    assert result.hazard_category == "fire/smoke"
    assert result.is_active is False
    assert result.skip_clarification is False
    assert result.recommended_action != "immediate_escalation"


def test_currently_active_smoke():
    router = FakeRouter(_result({"hazard_category": "fire/smoke", "location": "Line 1", "is_active": True}))
    result = _analyze("The machine started smoking five minutes ago and still is.", router)
    assert result.is_active is True
    assert result.skip_clarification is True


def test_people_counts():
    assert normalize_people_exposed("three workers are nearby") == 3
    assert normalize_people_exposed("around 5 people") == 5
    assert normalize_people_exposed(None) is None
    router = FakeRouter(
        _result({"hazard_category": "missing PPE", "location": "Bay 4", "people_exposed": 2, "is_active": True})
    )
    result = _analyze("Two workers are welding without safety glasses in Bay 4.", router)
    assert result.people_exposed == 2
    assert result.hazard_category == "missing PPE"


def test_multi_hazard_primary_and_secondary():
    router = FakeRouter(
        _result(
            {
                "hazard_category": "electrical",
                "location": "floor",
                "is_active": True,
                "secondary_hazards": ["slip/trip"],
            }
        )
    )
    result = _analyze("There is oil on the floor next to a machine with exposed wires.", router)
    assert result.hazard_category == "electrical"
    assert "slip/trip" in result.secondary_hazards


def test_injury_summary():
    router = FakeRouter(
        _result(
            {
                "hazard_category": "electrical",
                "location": "near Machine 8",
                "people_exposed": 1,
                "is_active": True,
                "already_injured": True,
                "injury_summary": "A worker reportedly received an electric shock.",
            }
        )
    )
    result = _analyze("A worker touched the exposed cable and received an electric shock near Machine 8.", router)
    assert result.already_injured is True
    assert result.injury_summary is not None
    assert "shock" in result.injury_summary.lower()


def test_has_image_true_and_false():
    router = FakeRouter(_result({"hazard_category": "machine", "location": "A", "is_active": True}))
    with_image = run(analyze_incident({"translated_text": "guard missing", "has_image": True}, call_model_fn=router))
    without = run(analyze_incident({"translated_text": "guard missing"}, call_model_fn=router))
    assert with_image.has_image is True
    assert without.has_image is False


def test_model_exception_fallback_keeps_qr():
    router = FakeRouter(TimeoutError("timeout"))
    result = run(
        analyze_incident(
            {"translated_text": "panel sparking", "qr_location": "Room 2", "qr_equipment": "B17"},
            call_model_fn=router,
        )
    )
    assert result.location == "Room 2"
    assert result.equipment_involved == "B17"
    assert result.hazard_category is None or result.skip_clarification is True


def test_invalid_json_fallback():
    router = FakeRouter(_result(content="not-json"))
    result = _analyze("oil on the floor", router)
    assert result.location is None
    assert result.needs_clarification is True or result.skip_clarification is False


def test_missing_model_fields():
    router = FakeRouter(ModelCallResult(content="{}", model="m", role="role_fast", paid=False))
    result = _analyze("wire spark near motor", router)
    assert result.hazard_category in {None, "other", "electrical"}


def test_empty_draft_asks_what_hazard():
    result = run(analyze_incident({"translated_text": "  "}, call_model_fn=FakeRouter(_result())))
    assert result.needs_clarification is True
    assert result.clarification_question == "What hazard did you notice?"


def test_follow_up_merges_location_and_does_not_null_category():
    session = Session("sess-1")
    first_router = FakeRouter(_result({"hazard_category": "slip/trip", "location": None, "is_active": True}))
    first = run(
        analyze_incident(
            {
                "translated_text": "Oil is spilled all over the floor and people are walking there.",
                "session_id": "sess-1",
            },
            session=session,
            call_model_fn=first_router,
        )
    )
    assert first.hazard_category == "slip/trip"
    assert first.clarification_question == "Where is this hazard?"
    second_router = FakeRouter(_result({"hazard_category": None, "location": "Packing Area 3", "is_active": True}))
    second = run(
        analyze_incident(
            {"translated_text": "Packing Area 3.", "session_id": "sess-1"},
            session=session,
            call_model_fn=second_router,
        )
    )
    assert second.hazard_category == "slip/trip"
    assert second.location == "Packing Area 3"
    assert second.clarification_question != "Where is this hazard?"


def test_none_and_empty_draft_do_not_crash():
    router = FakeRouter(_result())
    empty = run(analyze_incident({}, call_model_fn=router))
    none = run(analyze_incident(None, call_model_fn=router))
    assert empty.needs_clarification is True
    assert none.clarification_question == "What hazard did you notice?"


def test_unknown_people_count_stays_none():
    router = FakeRouter(
        _result({"hazard_category": "slip/trip", "location": "Hall", "people_exposed": None, "is_active": True})
    )
    result = _analyze("Everyone in the room is walking through the oil.", router)
    assert result.people_exposed is None
    assert normalize_people_exposed("everyone in the room") is None


def test_approximate_people_count_from_model_string():
    router = FakeRouter(_result({"hazard_category": "slip/trip", "location": "Bay", "people_exposed": "around 5"}))
    result = _analyze("around 5 people near the spill", router)
    assert result.people_exposed == 5


def test_no_longer_smoking_is_not_active_emergency():
    router = FakeRouter(_result({"hazard_category": "fire/smoke", "location": "Line", "is_active": False}))
    result = _analyze("The machine is no longer smoking.", router)
    assert result.is_active is False
    assert result.skip_clarification is False


def test_worker_urgency_does_not_alone_skip_clarification():
    router = FakeRouter(_result({"hazard_category": "slip/trip", "location": None, "is_active": True}))
    result = _analyze("urgent oil on the floor please help", router)
    assert result.worker_reports_urgent is True
    assert result.skip_clarification is False
    assert result.clarification_question == "Where is this hazard?"


def test_equipment_state_and_recommended_action_priority():
    router = FakeRouter(
        _result(
            {
                "hazard_category": "machine",
                "location": "Line 2",
                "is_active": True,
                "equipment_state": "running",
                "severity": "high",
            }
        )
    )
    result = _analyze("The conveyor is still running with the guard removed.", router)
    assert result.equipment_state == "running"
    assert result.needs_clarification is False
    assert result.recommended_action == "priority_review"


def test_fallback_emergency_still_escalates():
    router = FakeRouter(TimeoutError("timeout"))
    result = _analyze("Fire is spreading near the generator.", router)
    assert result.skip_clarification is True
    assert result.recommended_action == "immediate_escalation"
    assert result.is_active is True


def test_preserves_incident_and_session_ids():
    router = FakeRouter(_result({"hazard_category": "other", "location": "Office", "is_active": False}))
    result = run(
        analyze_incident(
            {
                "translated_text": "A light is flickering in the office.",
                "session_id": "+94770000000",
                "incident_id": "inc-9",
                "worker_phone": "+94770000000",
            },
            call_model_fn=router,
            incident_id="inc-9",
        )
    )
    assert result.session_id == "+94770000000"
    assert result.incident_id == "inc-9"
    assert result.worker_phone == "+94770000000"


def test_intake_result_accepted():
    router = FakeRouter(_result({"hazard_category": "chemical", "location": "storeroom", "is_active": True}))
    draft = IntakeResult(
        raw_text="chemical smell",
        translated_text="There is a chemical smell near the store room.",
        language="en",
        is_hazard_report=True,
        session_id="+94770000000",
    )
    result = run(analyze_incident(draft, call_model_fn=router))
    assert result.session_id == "+94770000000"
    assert result.hazard_category == "chemical"


def test_normalize_helpers():
    assert normalize_hazard_category("FIRE") == "fire/smoke"
    assert generate_clarification_question("location") == "Where is this hazard?"
