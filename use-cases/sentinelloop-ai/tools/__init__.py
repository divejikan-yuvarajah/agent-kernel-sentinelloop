"""SentinelLoop deterministic tools package.

Application-owned policies: risk arithmetic, incident persistence
interfaces, retrieval wrappers, assignment, evidence, idempotency,
lifecycle validation, and observability helpers.

Model calls go through ``call_model`` only — never OpenRouter directly.

Bind later with OpenAIToolBuilder.bind. Access session via ToolContext.get().
No Agent Kernel imports in this scaffold.
"""

from .guidance_tools import load_guidance_lines
from .model_router import ModelCallResult, call_model
from .risk_tools import calculate_risk

__all__ = ["ModelCallResult", "call_model", "calculate_risk", "load_guidance_lines"]
