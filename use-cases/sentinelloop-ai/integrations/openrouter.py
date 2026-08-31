"""OpenRouter application boundary.

Agents must not call OpenRouter (or any model provider) directly.

    Agents → tools.model_router.call_model(role, messages, **kwargs)

The router owns live catalog discovery, free-first selection, fallback,
and OPENROUTER_BUDGET_CEILING_USD enforcement.
"""

from tools.model_router import ModelCallResult, call_model, get_router

__all__ = ["ModelCallResult", "call_model", "get_router"]
