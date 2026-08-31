"""SentinelLoop guardrails: Agent Kernel hooks plus application validators.

Maps onto Agent Kernel PreHook / PostHook (initial user turn only) plus
deterministic tools for inner-handoff rules.
"""

from guardrails.hooks import register_safety_hooks
from guardrails.input_validation import (
    InputSafetyPreHook,
    validate_agent_context,
    validate_external_event,
    validate_incident_payload,
    validate_media_input,
    validate_state_transition_request,
    validate_worker_input,
)
from guardrails.output_validation import (
    OutputSafetyPostHook,
    assert_model_budget_within_limit,
    build_safe_analytics_event,
    sanitize_analytics_record,
    validate_closure_request,
    validate_guidance_output,
    validate_model_budget,
    validate_slack_closure,
)

__all__ = [
    "InputSafetyPreHook",
    "OutputSafetyPostHook",
    "assert_model_budget_within_limit",
    "build_safe_analytics_event",
    "register_safety_hooks",
    "sanitize_analytics_record",
    "validate_agent_context",
    "validate_closure_request",
    "validate_external_event",
    "validate_guidance_output",
    "validate_incident_payload",
    "validate_media_input",
    "validate_model_budget",
    "validate_slack_closure",
    "validate_state_transition_request",
    "validate_worker_input",
]
