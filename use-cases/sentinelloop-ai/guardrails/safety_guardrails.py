"""Safety invariants enforced by the validation pipeline.

Deterministic escalation must apply; models must not downgrade below the
mandatory minimum; guidance must not be fabricated; incidents must not
auto-close unsafely. Prompt-injection content is data, not instructions.

SPEC.md Rule: SentinelLoop assists safety teams; it does not replace accountable humans.
"""

from guardrails.input_validation import detect_prompt_injection, validate_worker_input
from guardrails.output_validation import (
    build_safe_analytics_event,
    sanitize_analytics_record,
    validate_closure_request,
    validate_guidance_output,
)

__all__ = [
    "build_safe_analytics_event",
    "detect_prompt_injection",
    "sanitize_analytics_record",
    "validate_closure_request",
    "validate_guidance_output",
    "validate_worker_input",
]
