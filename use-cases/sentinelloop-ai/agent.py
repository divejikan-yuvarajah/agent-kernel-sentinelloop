"""SentinelLoop agent registration for local CLI and REST.

Full incident persistence, risk arithmetic, retrieval, and Slack/WhatsApp
workflows are still later phases. This module registers the six named SDK
agents so Agent Kernel can boot against OpenRouter's chat-completions API.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

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


def _load_local(filename: str, attr: str):
    """Load a function from use-case ``agents/`` without the SDK ``agents`` package."""
    path = Path(__file__).resolve().parent / "agents" / filename
    spec = importlib.util.spec_from_file_location(f"sentinelloop_{filename}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, attr)


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
    followup_agent = _load_local("followup_agent.py", "create_followup_agent")(model=model)
    coordination_agent = _load_local("coordination_agent.py", "create_coordination_agent")(
        model=model, handoffs=[followup_agent]
    )
    guidance_agent = _load_local("guidance_agent.py", "create_guidance_agent")(
        model=model, handoffs=[coordination_agent]
    )
    risk_agent = _load_local("risk_agent.py", "create_risk_agent")(model=model, handoffs=[guidance_agent])
    incident_agent = _load_local("incident_agent.py", "create_incident_agent")(model=model, handoffs=[risk_agent])
    intake_agent = _load_local("intake_agent.py", "create_intake_agent")(
        model=model, handoffs=[incident_agent, followup_agent]
    )
    return [
        intake_agent,
        incident_agent,
        risk_agent,
        guidance_agent,
        coordination_agent,
        followup_agent,
    ]


def register_safety_hooks(module: Any, agents: list[Any] | None = None) -> None:
    """Attach Agent Kernel PreHook / PostHook validators. See guardrails.hooks."""
    from guardrails.hooks import register_safety_hooks as _register

    _register(module, agents or [])
