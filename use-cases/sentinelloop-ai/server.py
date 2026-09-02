"""Local REST API for SentinelLoop AI (SPEC: REST, not Lambda)."""

import logging
import os
import threading

from dotenv import load_dotenv

load_dotenv()

from ak_bootstrap import pin_openai_agents_sdk

pin_openai_agents_sdk()

from agentkernel.api import RESTAPI
from agentkernel.openai import OpenAIModule
from agentkernel.slack import AgentSlackRequestHandler

from agent import build_agents, configure_model_provider, register_safety_hooks
from dashboard.api import DashboardHandler
from integrations.telegram_handler import SentinelLoopTelegramHandler, run_polling, telegram_bot_token

log = logging.getLogger("sentinelloop.server")

configure_model_provider()
_agents = build_agents()
register_safety_hooks(OpenAIModule(_agents), _agents)


def _maybe_start_telegram_polling() -> None:
    """Start long-polling when TELEGRAM_MODE=polling (default for local demo)."""
    mode = (os.environ.get("TELEGRAM_MODE") or "polling").strip().lower()
    if mode != "polling":
        log.info("Telegram polling skipped (TELEGRAM_MODE=%s)", mode)
        return
    if not telegram_bot_token():
        log.warning("Telegram polling skipped (no bot token configured)")
        return

    def _poll() -> None:
        try:
            run_polling()
        except Exception:
            log.exception("Telegram polling stopped")

    thread = threading.Thread(target=_poll, name="telegram-polling", daemon=True)
    thread.start()
    log.info("Telegram polling started in background (TELEGRAM_MODE=polling)")


def _rest_handlers():
    """Dashboard always mounts. Telegram/Slack skip when tokens are missing."""
    handlers = [DashboardHandler()]
    try:
        handlers.append(SentinelLoopTelegramHandler())
    except ValueError as exc:
        log.warning("Telegram handler disabled (%s). Dashboard API still runs.", exc)
    try:
        handlers.append(AgentSlackRequestHandler())
    except Exception as exc:
        log.warning("Slack handler disabled (%s). Dashboard API still runs.", exc)
    return handlers


if __name__ == "__main__":
    _maybe_start_telegram_polling()
    RESTAPI.run(_rest_handlers())
