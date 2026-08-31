"""Slack integration boundary.

Outbound coordination alerts live in ``slack_handler.py`` (application
``slack_sdk`` client). Inbound Events API verification and routing remain
with Agent Kernel ``AgentSlackRequestHandler``. Notification delivered is
not human acknowledgement.
"""

from integrations.slack_handler import SlackHandler, SlackPostError, parse_thread_command, sanitize_slack_text

__all__ = ["SlackHandler", "SlackPostError", "parse_thread_command", "sanitize_slack_text"]
