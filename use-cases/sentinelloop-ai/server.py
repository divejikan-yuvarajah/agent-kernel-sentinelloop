"""Local REST API for SentinelLoop AI (SPEC: REST, not Lambda)."""

from dotenv import load_dotenv

load_dotenv()

from ak_bootstrap import pin_openai_agents_sdk

pin_openai_agents_sdk()

from agentkernel.api import RESTAPI
from agentkernel.openai import OpenAIModule

from agent import build_agents, configure_model_provider

configure_model_provider()
OpenAIModule(build_agents())

if __name__ == "__main__":
    RESTAPI.run()
