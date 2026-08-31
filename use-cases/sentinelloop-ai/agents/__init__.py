"""SentinelLoop agent package.

``intake_agent`` is implemented. Other specialists remain placeholders until
their phases. Import ``create_intake_agent`` / ``process_intake``; do not
construct network clients at package import.
"""

from .intake_agent import IntakeResult, create_intake_agent, process_intake

__all__ = ["IntakeResult", "create_intake_agent", "process_intake"]
