"""SentinelLoop agent package.

``intake_agent`` and ``incident_agent`` are implemented. Later specialists remain
placeholders. Do not construct network clients at package import.
"""

from .incident_agent import IncidentAnalysis, analyze_incident, create_incident_agent
from .intake_agent import IntakeResult, create_intake_agent, process_intake

__all__ = [
    "IntakeResult",
    "create_intake_agent",
    "process_intake",
    "IncidentAnalysis",
    "analyze_incident",
    "create_incident_agent",
]
