"""Required intake coverage. Complements tests/test_intake_agent.py.

Language detection, hazard classification, and QR prefix extraction.
call_model is always mocked.
"""

from __future__ import annotations

import json

from agentkernel.core.session.in_memory import InMemorySessionStore

from agents.incident_agent import analyze_incident
from agents.intake_agent import parse_qr_prefix, process_intake
from tests.conftest import MockModelRouter, run
from tools.model_router import ModelCallResult


def _intake_result(**kwargs) -> ModelCallResult:
    payload = {
        "language": kwargs.pop("language", "en"),
        "translated_text": kwargs.pop("translated_text", "There is a hazard."),
        "is_hazard_report": kwargs.pop("is_hazard_report", True),
        "language_confidence": "high",
        "hazard_confidence": "high",
        "needs_clarification": False,
    }
    return ModelCallResult(content=json.dumps(payload), model="mock/free", role="role_fast", paid=False)


def _incident_result(**kwargs) -> ModelCallResult:
    payload = {
        "hazard_category": kwargs.pop("hazard_category", "electrical"),
        "location": kwargs.pop("location", None),
        "equipment_involved": kwargs.pop("equipment_involved", None),
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
            "location": 0.8,
            "equipment_involved": 0.8,
            "people_exposed": 0.1,
            "is_active": 0.8,
            "already_injured": 0.9,
        },
        "evidence": {},
    }
    payload.update(kwargs)
    return ModelCallResult(content=json.dumps(payload), model="mock/free", role="role_fast", paid=False)


def test_english_language_detection(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(
        language="en", translated_text="There is smoke near the machine", is_hazard_report=True
    )
    result = run(
        process_intake(
            "94770000001",
            sample_worker_messages["en"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert result.language == "en"
    assert result.is_hazard_report is True
    assert mock_model_router.calls[0][0] == "role_fast"


def test_sinhala_language_detection(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(
        language="si", translated_text="There is an exposed wire on the road.", is_hazard_report=True
    )
    result = run(
        process_intake(
            "94770000002",
            sample_worker_messages["si"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert result.language == "si"
    assert result.raw_text == sample_worker_messages["si"]
    assert result.is_hazard_report is True


def test_tamil_language_detection(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(
        language="ta", translated_text="There is an oil leak near the packing machine.", is_hazard_report=True
    )
    result = run(
        process_intake(
            "94770000003",
            sample_worker_messages["ta"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert result.language == "ta"
    assert result.raw_text == sample_worker_messages["ta"]


def test_mixed_language_detection(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(
        language="mixed", translated_text="There is an oil leak and smoke at packing line 2.", is_hazard_report=True
    )
    result = run(
        process_intake(
            "94770000004",
            sample_worker_messages["mixed"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert result.language == "mixed"
    assert result.is_mixed_language is True


def test_electrical_hazard_classification(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(
        language="en", translated_text=sample_worker_messages["electrical"], is_hazard_report=True
    )
    intake = run(
        process_intake(
            "94770000005",
            sample_worker_messages["electrical"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert intake.is_hazard_report is True
    incident_router = MockModelRouter(_incident_result(hazard_category="electrical"))
    extracted = run(analyze_incident(intake, call_model_fn=incident_router))
    assert extracted.hazard_category == "electrical"


def test_fire_smoke_hazard_classification(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(
        language="en", translated_text=sample_worker_messages["fire"], is_hazard_report=True
    )
    intake = run(
        process_intake(
            "94770000006",
            sample_worker_messages["fire"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert intake.is_hazard_report is True
    incident_router = MockModelRouter(_incident_result(hazard_category="fire/smoke"))
    extracted = run(analyze_incident(intake, call_model_fn=incident_router))
    assert extracted.hazard_category == "fire/smoke"


def test_chemical_hazard_classification(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(
        language="en", translated_text=sample_worker_messages["chemical"], is_hazard_report=True
    )
    intake = run(
        process_intake(
            "94770000007",
            sample_worker_messages["chemical"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert intake.is_hazard_report is True
    incident_router = MockModelRouter(_incident_result(hazard_category="chemical"))
    extracted = run(analyze_incident(intake, call_model_fn=incident_router))
    assert extracted.hazard_category == "chemical"


def test_greeting_is_not_a_hazard_report(mock_model_router, sample_worker_messages):
    mock_model_router.response = _intake_result(language="en", translated_text="Good morning", is_hazard_report=False)
    result = run(
        process_intake(
            "94770000008",
            sample_worker_messages["greeting"],
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert result.is_hazard_report is False


def test_qr_prefix_extracted_stripped_and_passed_to_incident(mock_model_router, sample_worker_messages):
    qr_text = sample_worker_messages["qr"]
    parsed = parse_qr_prefix(qr_text)
    assert parsed.valid is True
    assert parsed.location == "Electrical Room"
    assert parsed.equipment == "Panel B17"
    assert "SLQR" not in parsed.human_text
    assert parsed.human_text == "There is smoke near the machine"

    mock_model_router.response = _intake_result(
        language="en", translated_text="There is smoke near the machine", is_hazard_report=True
    )
    intake = run(
        process_intake(
            "94770000009",
            qr_text,
            session_store=InMemorySessionStore(),
            call_model_fn=mock_model_router,
        )
    )
    assert intake.qr_location == "Electrical Room"
    assert intake.qr_equipment == "Panel B17"
    user_blob = mock_model_router.calls[0][1][1]["content"]
    assert "There is smoke near the machine" in user_blob
    assert 'location="Electrical Room"' not in user_blob.split("WORKER_MESSAGE_END")[0]

    incident_router = MockModelRouter(
        _incident_result(hazard_category="fire/smoke", location="Electrical Room", equipment_involved="Panel B17")
    )
    extracted = run(analyze_incident(intake, call_model_fn=incident_router))
    prompt = incident_router.calls[0][1][1]["content"]
    assert "STRUCTURED_QR_METADATA_START" in prompt
    assert "qr_location=Electrical Room" in prompt
    assert "qr_equipment=Panel B17" in prompt
    assert extracted.qr_location == "Electrical Room" or extracted.location == "Electrical Room"
