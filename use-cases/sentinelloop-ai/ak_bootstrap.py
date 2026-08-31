"""Load the OpenAI Agents SDK despite the local agents/ directory.

The SentinelLoop layout uses ``agents/`` for application placeholders. That
name collides with the SDK package ``agents``. Pin the SDK in sys.modules
before Agent Kernel imports it.
"""

from __future__ import annotations

import sys
from pathlib import Path


def pin_openai_agents_sdk() -> None:
    root = Path(__file__).resolve().parent
    filtered = [p for p in sys.path if Path(p).resolve() != root]
    previous = list(sys.path)
    sys.path[:] = filtered
    sys.modules.pop("agents", None)
    import agents as sdk  # noqa: F401  # OpenAI Agents SDK

    sys.modules["agents"] = sdk
    sys.path[:] = previous
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
