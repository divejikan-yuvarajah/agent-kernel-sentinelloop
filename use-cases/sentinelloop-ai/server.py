"""Local REST API for SentinelLoop AI (SPEC: REST, not Lambda)."""

import logging

from dotenv import load_dotenv

load_dotenv()

from ak_bootstrap import pin_openai_agents_sdk

pin_openai_agents_sdk()

from agentkernel.api import RESTAPI
from agentkernel.openai import OpenAIModule
from agentkernel.slack import AgentSlackRequestHandler

from agent import build_agents, configure_model_provider, register_safety_hooks
from dashboard.api import DashboardHandler
from integrations.whatsapp_handler import SentinelLoopWhatsAppHandler

log = logging.getLogger("sentinelloop.server")

configure_model_provider()
_agents = build_agents()
register_safety_hooks(OpenAIModule(_agents), _agents)


def _rest_handlers():
    """Dashboard always mounts. WhatsApp/Slack skip when tokens are missing."""
    handlers = [DashboardHandler()]
    try:
        handlers.append(SentinelLoopWhatsAppHandler())
    except ValueError as exc:
        log.warning("WhatsApp handler disabled (%s). Dashboard API still runs.", exc)
    try:
        handlers.append(AgentSlackRequestHandler())
    except Exception as exc:
        log.warning("Slack handler disabled (%s). Dashboard API still runs.", exc)
    return handlers


if __name__ == "__main__":
    RESTAPI.run(_rest_handlers())
