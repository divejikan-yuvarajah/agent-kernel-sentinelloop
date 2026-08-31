"""Register SentinelLoop validators on the real Agent Kernel PreHook / PostHook API."""

from __future__ import annotations

from typing import Any

from guardrails.input_validation import InputSafetyPreHook
from guardrails.output_validation import OutputSafetyPostHook


def register_safety_hooks(module: Any, agents: list[Any]) -> None:
    """Attach input PreHook to intake_agent and output PostHook to every agent.

    Agent Kernel 0.6.0 runs hooks only on the initial user turn, not inner SDK
    handoffs. Guidance, closure, privacy, and budget checks also run inside
    application functions.
    """
    if module is None or not agents:
        return
    intake = next((agent for agent in agents if getattr(agent, "name", None) == "intake_agent"), None)
    if intake is not None:
        module.pre_hook(intake, [InputSafetyPreHook()])
    post = OutputSafetyPostHook()
    for agent in agents:
        if getattr(agent, "name", None):
            module.post_hook(agent, [post])
