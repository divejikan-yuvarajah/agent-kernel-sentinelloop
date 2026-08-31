"""Output validation via Agent Kernel PostHook and application validators.

Structured extraction checks, model-output sanity, valid risk ranges, and
tool-result consistency. PostHook sees only the final user-facing reply,
not inner risk_agent handoffs — persist official risk from the tool.
"""

from guardrails.output_validation import (
    OutputSafetyPostHook,
    validate_closure_request,
    validate_guidance_output,
    validate_slack_closure,
)

__all__ = [
    "OutputSafetyPostHook",
    "validate_closure_request",
    "validate_guidance_output",
    "validate_slack_closure",
]
