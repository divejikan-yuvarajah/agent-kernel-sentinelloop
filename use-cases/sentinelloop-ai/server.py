"""Local REST API for SentinelLoop AI (SPEC: REST, not Lambda)."""

from dotenv import load_dotenv

load_dotenv()

from ak_bootstrap import pin_openai_agents_sdk

pin_openai_agents_sdk()

from agentkernel.api import RESTAPI
from agentkernel.openai import OpenAIModule
from agentkernel.slack import AgentSlackRequestHandler

from agent import build_agents, configure_model_provider
from dashboard.api import DashboardHandler
from integrations.whatsapp_handler import SentinelLoopWhatsAppHandler

configure_model_provider()
OpenAIModule(build_agents())

if __name__ == "__main__":
    RESTAPI.run(
        [
            DashboardHandler(),
            SentinelLoopWhatsAppHandler(),
            AgentSlackRequestHandler(),
        ]
    )
