"""Incident status transition enforcement.

Reject invalid durable updates (for example CLOSED from IN_PROGRESS).
Complements tools/lifecycle.py; persistence must validate latest state.

SPEC.md Rule: Reject invalid durable updates (for example CLOSED from IN_PROGRESS).
"""

from guardrails.input_validation import validate_state_transition_request

__all__ = ["validate_state_transition_request"]
