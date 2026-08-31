"""Local Agent Kernel CLI for SentinelLoop AI."""

from dotenv import load_dotenv

load_dotenv()

from ak_bootstrap import pin_openai_agents_sdk

pin_openai_agents_sdk()

from agentkernel.cli import CLI
from agentkernel.openai import OpenAIModule

from agent import build_agents, configure_model_provider

configure_model_provider()
OpenAIModule(build_agents())

if __name__ == "__main__":
    CLI.main()
