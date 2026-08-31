"""SentinelLoop agent package.

``intake_agent``, ``incident_agent``, ``risk_agent``, and ``guidance_agent``
are implemented. Later specialists remain placeholders. Do not construct
network clients at package import.
"""

from .guidance_agent import GuidanceResult, create_guidance_agent, generate_guidance
from .incident_agent import IncidentAnalysis, analyze_incident, create_incident_agent
from .intake_agent import IntakeResult, create_intake_agent, process_intake
from .risk_agent import RiskAssessment, assess_risk, create_risk_agent

__all__ = [
    "IntakeResult",
    "create_intake_agent",
    "process_intake",
    "IncidentAnalysis",
    "analyze_incident",
    "create_incident_agent",
    "RiskAssessment",
    "assess_risk",
    "create_risk_agent",
    "GuidanceResult",
    "generate_guidance",
    "create_guidance_agent",
]
