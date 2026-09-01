"""Output validation tests. No live OpenRouter, Telegram, or Slack."""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from guardrails.events import EVENT_GUIDANCE_BLOCKED, list_guardrail_events, reset_guardrail_events
from guardrails.output_validation import (
    assert_model_budget_within_limit,
    build_safe_analytics_event,
    sanitize_analytics_record,
    validate_closure_request,
    validate_guidance_output,
    validate_model_budget,
    validate_slack_closure,
)

KB = """
- Keep away from exposed wires, sparks, smoke, or damaged electrical equipment.
- Do not touch the damaged equipment, cables, or nearby metal parts.
- Warn nearby workers to stay away from the dangerous area.
"""


def setup_function() -> None:
    reset_guardrail_events()


def test_valid_knowledge_base_sentence_passes():
    result = validate_guidance_output(
        "Keep away from exposed wires, sparks, smoke, or damaged electrical equipment.",
        KB,
        knowledge_base_file="electrical_safety.md",
    )
    assert result["approved"] is True
    assert result["violations"] == []
    assert result["matched_lines"]
    assert result["confidence"] >= 0.5


def test_safe_paraphrase_passes():
    result = validate_guidance_output(
        "Stay away from exposed wires, sparks, smoke, or damaged electrical equipment.",
        KB,
        knowledge_base_file="electrical_safety.md",
    )
    assert result["approved"] is True


def test_invented_instruction_is_blocked():
    result = validate_guidance_output(
        "Disconnect the main breaker yourself.",
        KB,
        knowledge_base_file="electrical_safety.md",
    )
    assert result["approved"] is False
    assert "Not supported by knowledge base." in result["violations"]
    events = list_guardrail_events()
    assert any(item.event == EVENT_GUIDANCE_BLOCKED for item in events)


def test_low_auto_close_allowed():
    result = validate_closure_request(risk_level="Low", source="telegram")
    assert result["approved"] is True
    assert result["human_review_required"] is False


def test_medium_auto_close_allowed():
    result = validate_closure_request(risk_level="Medium", source="auto")
    assert result["approved"] is True


def test_high_auto_close_blocked():
    result = validate_closure_request(risk_level="High", source="telegram")
    assert result["approved"] is False
    assert result["human_review_required"] is True


def test_critical_auto_close_blocked():
    result = validate_closure_request(risk_level="Critical", source="telegram")
    assert result["approved"] is False


def test_critical_slack_closed_allowed():
    result = validate_closure_request(
        risk_level="Critical",
        source="slack",
        reviewed_by_human=True,
        slack_closed_action={"closed_by": "U12345", "source": "slack", "action": "Closed"},
    )
    assert result["approved"] is True


def test_slack_closure_rejects_unrelated_thread():
    result = validate_slack_closure(
        action="Closed",
        actor="U1",
        incident_id="INC-1",
        expected_incident_id="INC-1",
        thread_ts="9.9",
        expected_thread_ts="1.0",
    )
    assert result["approved"] is False


def test_slack_closure_rejects_unauthorized_and_wrong_action():
    assert (
        validate_slack_closure(action="Accept", actor="U1", incident_id="INC-1", expected_incident_id="INC-1")[
            "approved"
        ]
        is False
    )
    assert (
        validate_slack_closure(action="Closed", actor=None, incident_id="INC-1", expected_incident_id="INC-1")[
            "approved"
        ]
        is False
    )


def test_anonymous_phone_removed_from_analytics():
    cleaned = sanitize_analytics_record(
        {
            "name": "Worker",
            "phone": "+94771234567",
            "category": "Electrical",
            "region": "Colombo",
            "is_anonymous": True,
        },
        is_anonymous=True,
    )
    assert "phone" not in cleaned
    assert cleaned["anonymous"] is True
    assert "+9477" not in str(cleaned)
    event = build_safe_analytics_event(
        {"name": "Worker", "phone": "+94771234567", "category": "Electrical", "region": "Colombo", "is_anonymous": True}
    )
    assert event["anonymous"] is True
    assert "phone" not in event
    assert event["region"] == "Colombo"
    assert event["category"] == "Electrical"


def test_non_anonymous_phone_allowed_operationally():
    operational = {"phone_number": "+94771234567", "is_anonymous": False, "category": "Fire"}
    assert operational["phone_number"] == "+94771234567"
    event = build_safe_analytics_event(operational)
    assert "phone_number" not in event
    assert event.get("reporter_present") is True


def test_privacy_leak_scan_redacts_stray_phone():
    cleaned = sanitize_analytics_record({"note": "call +94771234567"}, is_anonymous=False)
    assert "+9477" not in str(cleaned.get("note"))


def test_budget_below_ceiling_passes(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BUDGET_CEILING_USD", "10")
    result = validate_model_budget(current_cost="3.00", requested_cost="1.00")
    assert result["approved"] is True
    assert_model_budget_within_limit("3.00")


def test_budget_above_ceiling_blocks(monkeypatch):
    monkeypatch.setenv("OPENROUTER_BUDGET_CEILING_USD", "5")
    result = validate_model_budget(current_cost="4.50", requested_cost="1.00")
    assert result["approved"] is False
    with pytest.raises(AssertionError):
        assert_model_budget_within_limit(Decimal("6.00"), ceiling="5")


def test_llm_judge_cannot_approve_invented_actions():
    from guardrails.output_validation import _optional_llm_judge

    assert _optional_llm_judge("Disconnect the main breaker yourself.", ["Keep away from exposed wires."]) is None
    blocked = validate_guidance_output("Disconnect the main breaker yourself.", "Move away from electrical equipment.")
    assert blocked["approved"] is False
