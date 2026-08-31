"""Required guidance, closure, and privacy guardrail tests.

Complements tests/test_input_validation.py and tests/test_output_validation.py.
"""

from __future__ import annotations

from uuid import uuid4

from agents.followup_agent import (
    ERROR_HUMAN_REVIEW,
    FollowupService,
    MemoryFollowupStore,
)
from guardrails.output_validation import (
    build_safe_analytics_event,
    sanitize_analytics_record,
    validate_closure_request,
    validate_guidance_output,
)
from integrations.slack_handler import SlackHandler
from integrations.whatsapp import WhatsAppHandler
from tests.conftest import FakeRepository, MockSlackClient, MockWhatsAppClient, run
from tools.lifecycle import STATUS_CLOSED, STATUS_RESOLVED


def _followup(repo: FakeRepository, whatsapp=None, slack=None) -> FollowupService:
    return FollowupService(
        whatsapp=WhatsAppHandler(client=whatsapp or MockWhatsAppClient()),
        slack=SlackHandler(client=slack or MockSlackClient()),
        repository=repo,
        store=MemoryFollowupStore(),
    )


def _incident(**kwargs) -> dict:
    base = {
        "incident_ref": "INC-0099",
        "id": str(uuid4()),
        "status": STATUS_RESOLVED,
        "worker_phone": "94770000000",
        "detected_language": "en",
        "location": "Electrical Room",
        "assigned_team": "Electrical Maintenance",
        "slack_channel_id": "C-ELEC",
        "slack_thread_ts": "1.000",
        "hazard_category": "electrical",
        "risk_level": "Low",
    }
    base.update(kwargs)
    return base


def test_guidance_hallucination_is_rejected(sample_knowledge_base):
    result = validate_guidance_output(
        "Turn off the electrical supply yourself.",
        sample_knowledge_base,
        knowledge_base_file="electrical_safety.md",
    )
    assert result["approved"] is False
    assert result["violations"]
    assert "Not supported by knowledge base." in result["violations"]


def test_guidance_exact_knowledge_base_sentence_is_approved(sample_knowledge_base):
    sentence = "Move away from the damaged equipment."
    result = validate_guidance_output(sentence, sample_knowledge_base, knowledge_base_file="electrical_safety.md")
    assert result["approved"] is True
    assert result["violations"] == []
    assert result["matched_lines"]


def test_guidance_close_paraphrase_is_accepted():
    kb = "Avoid entering the affected area."
    result = validate_guidance_output(
        "Stay away from the affected area.",
        kb,
        knowledge_base_file="area_control.md",
    )
    assert result["approved"] is True


def test_critical_worker_confirm_blocks_auto_close():
    blocked = validate_closure_request(risk_level="Critical", source="whatsapp")
    assert blocked["approved"] is False
    assert blocked["human_review_required"] is True

    repo = FakeRepository()
    repo.risk_level = "Critical"
    repo.incident_status = "RESOLVED"
    service = _followup(repo)
    incident = _incident(risk_level="Critical", incident_ref="INC-CRIT")
    run(service.start_worker_verification(incident))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-CRIT"))
    assert result.closed is False
    assert result.error == ERROR_HUMAN_REVIEW
    assert result.status != STATUS_CLOSED
    assert repo.incident_status != "CLOSED"


def test_low_worker_confirm_allows_auto_close():
    allowed = validate_closure_request(risk_level="Low", source="whatsapp")
    assert allowed["approved"] is True
    assert allowed["human_review_required"] is False

    repo = FakeRepository()
    repo.risk_level = "Low"
    service = _followup(repo)
    incident = _incident(risk_level="Low", incident_ref="INC-LOW")
    run(service.start_worker_verification(incident))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-LOW"))
    assert result.closed is True
    assert result.status == STATUS_CLOSED
    assert result.resolution_timestamp is not None
    assert repo.closed_at is not None


def test_anonymous_analytics_omit_phone_and_whatsapp_id():
    cleaned = sanitize_analytics_record(
        {
            "phone_number": "+94771234567",
            "whatsapp_id": "94771234567",
            "category": "electrical",
            "region": "Colombo",
            "is_anonymous": True,
        },
        is_anonymous=True,
    )
    assert "phone_number" not in cleaned
    assert "whatsapp_id" not in cleaned
    assert "+9477" not in str(cleaned)
    event = build_safe_analytics_event(
        {
            "phone_number": "+94771234567",
            "whatsapp_id": "94771234567",
            "category": "electrical",
            "region": "Colombo",
            "is_anonymous": True,
        }
    )
    assert "phone_number" not in event
    assert "whatsapp_id" not in event
    assert event["anonymous"] is True


def test_non_anonymous_operational_storage_may_keep_phone():
    operational = {
        "phone_number": "+94771234567",
        "whatsapp_id": "94771234567",
        "is_anonymous": False,
        "category": "fire/smoke",
    }
    assert operational["phone_number"] == "+94771234567"
    analytics = build_safe_analytics_event(operational)
    assert "phone_number" not in analytics
    assert "whatsapp_id" not in analytics
    assert analytics.get("reporter_present") is True


def test_guardrail_package_reexports_are_importable():
    from guardrails import (
        budget_guardrails,
        input_guardrails,
        lifecycle_guardrails,
        output_guardrails,
        safety_guardrails,
    )

    assert budget_guardrails.validate_model_budget is not None
    assert input_guardrails.validate_worker_input is not None
    assert output_guardrails.validate_guidance_output is not None
    assert safety_guardrails.detect_prompt_injection is not None
    assert lifecycle_guardrails.validate_state_transition_request is not None


def test_register_safety_hooks_attaches_pre_and_post():
    from types import SimpleNamespace

    from guardrails.hooks import register_safety_hooks

    pre_calls = []
    post_calls = []

    class Module:
        def pre_hook(self, agent, hooks):
            pre_calls.append((agent.name, hooks))

        def post_hook(self, agent, hooks):
            post_calls.append((agent.name, hooks))

    agents = [
        SimpleNamespace(name="intake_agent"),
        SimpleNamespace(name="guidance_agent"),
        SimpleNamespace(name="followup_agent"),
    ]
    register_safety_hooks(None, agents)
    assert pre_calls == []
    register_safety_hooks(Module(), [])
    assert pre_calls == []
    register_safety_hooks(Module(), agents)
    assert pre_calls[0][0] == "intake_agent"
    assert {name for name, _hooks in post_calls} == {"intake_agent", "guidance_agent", "followup_agent"}
