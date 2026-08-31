"""Model-budget operational policy.

Paid OpenRouter spend is governed by ``tools.model_router`` using
OPENROUTER_BUDGET_CEILING_USD and ``.runtime/spend_ledger.json``.

This module does not reset the ledger. Agents must not expose a budget-reset
tool. After the ceiling, the router returns ``budget_limited=true`` and
best-effort free capacity; Critical safety reports must still be preserved
and escalated on deterministic / human paths.

SPEC.md Rule: Paid OpenRouter spend is governed by OPENROUTER_BUDGET_CEILING_USD.
"""

from guardrails.output_validation import assert_model_budget_within_limit, validate_model_budget

__all__ = ["assert_model_budget_within_limit", "validate_model_budget"]
