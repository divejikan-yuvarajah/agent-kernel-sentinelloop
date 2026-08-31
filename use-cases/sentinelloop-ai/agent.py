"""SentinelLoop agent registration for local CLI and REST.

Full incident persistence, risk arithmetic, retrieval, and Slack/WhatsApp
workflows are still later phases. This module registers the six named SDK
agents so Agent Kernel can boot against OpenRouter's chat-completions API.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from openai import AsyncOpenAI

from agents import Agent, OpenAIChatCompletionsModel, set_tracing_disabled

SHARED = (
    "You are part of SentinelLoop AI, a workplace hazard reporting system. "
    "Workers may write in Sinhala, Tamil, English, or mixed language. "
    "Do not invent safety procedures. Do not compute a numeric risk score. "
    "Do not claim an incident was saved, assigned, or closed unless a tool did it. "
    "Keep replies short and practical."
)

_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1"


def _load_create_intake_agent():
    """Load local agents/intake_agent.py without the SDK ``agents`` package."""
    path = Path(__file__).resolve().parent / "agents" / "intake_agent.py"
    spec = importlib.util.spec_from_file_location("sentinelloop_intake_agent", path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load intake_agent module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_intake_agent


def configure_model_provider() -> None:
    """Point the OpenAI Agents SDK at OpenRouter chat completions."""
    set_tracing_disabled(True)
    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if or_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = or_key
    if or_key:
        os.environ.setdefault("OPENAI_BASE_URL", os.environ.get("OPENROUTER_BASE_URL") or _OPENROUTER_CHAT_URL)


def _chat_model() -> OpenAIChatCompletionsModel:
    configure_model_provider()
    api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL") or _OPENROUTER_CHAT_URL
    model_id = (os.environ.get("OPENROUTER_MODEL") or "").strip() or "mistralai/mistral-nemo"
    client = AsyncOpenAI(api_key=api_key or "missing-openai-key", base_url=base_url, timeout=60.0)
    return OpenAIChatCompletionsModel(model=model_id, openai_client=client)


def build_agents() -> list[Agent]:
    model = _chat_model()
    followup_agent = Agent(
        name="followup_agent",
        handoff_description="Verifies remediation with the original worker and closes or reopens the same incident.",
        instructions=(
            f"{SHARED} You are followup_agent. Ask whether the reported hazard is still present. "
            "Do not close an incident yourself."
        ),
        model=model,
    )
    coordination_agent = Agent(
        name="coordination_agent",
        handoff_description="Routes incidents to the safety team and records assignment intent.",
        instructions=(
            f"{SHARED} You are coordination_agent. Describe who should be notified. "
            "Do not treat a message as proof that a human acknowledged the alert. "
            "Handoff to followup_agent when the worker should be asked to verify a fix."
        ),
        handoffs=[followup_agent],
        model=model,
    )
    guidance_agent = Agent(
        name="guidance_agent",
        handoff_description="Retrieves approved safety guidance; never invents procedures.",
        instructions=(
            f"{SHARED} You are guidance_agent. If no approved guidance was retrieved, say so clearly. "
            "Handoff to coordination_agent next."
        ),
        handoffs=[coordination_agent],
        model=model,
    )
    risk_agent = Agent(
        name="risk_agent",
        handoff_description="Estimates severity and likelihood; deterministic code owns the official score.",
        instructions=(
            f"{SHARED} You are risk_agent. You may discuss severity and likelihood in words. "
            "You must not output risk_score = severity × likelihood as an official result. "
            "Handoff to guidance_agent next."
        ),
        handoffs=[guidance_agent],
        model=model,
    )
    incident_agent = Agent(
        name="incident_agent",
        handoff_description="Extracts structured incident facts. Unknown is not false.",
        instructions=(
            f"{SHARED} You are incident_agent. Extract hazard description, location, and whether "
            "injury, active danger, or people exposed were stated. Missing facts stay unknown. "
            "Handoff to risk_agent when you have a usable description."
        ),
        handoffs=[risk_agent],
        model=model,
    )
    intake_agent = _load_create_intake_agent()(model=model, handoffs=[incident_agent, followup_agent])
    return [
        intake_agent,
        incident_agent,
        risk_agent,
        guidance_agent,
        coordination_agent,
        followup_agent,
    ]
