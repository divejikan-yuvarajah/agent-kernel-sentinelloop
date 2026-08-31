"""Application-level Slack transport for SentinelLoop coordination.

Outbound alerts use slack_sdk AsyncWebClient.chat_postMessage (SPEC).
AgentSlackRequestHandler is inbound Events API only — it has no send_alert
and no block_actions router. Interactive buttons are included in outbound
Block Kit; thread keywords are the supported inbound command path.

Never hard-code bot tokens or channel secrets.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from tools.assignment_tools import (
    STATUS_IN_PROGRESS,
    STATUS_RESOLVED,
    format_category_display,
    format_recommended_action,
    resolve_team_destination,
    resolve_team_name,
)

log = logging.getLogger("sentinelloop.slack")

ACTION_ACCEPT = "incident_accept"
ACTION_REASSIGN = "incident_reassign"
ACTION_ESCALATE = "incident_escalate"
ACTION_CLOSED = "incident_closed"
PERMANENT_SLACK_ERRORS = frozenset({"invalid_auth", "channel_not_found", "not_in_channel", "invalid_arguments"})
MENTION_RE = re.compile(
    r"<!channel>|<!here>|<!everyone>|<@[^>]+>|@channel|@here|@everyone",
    re.I,
)
MAX_DESCRIPTION_CHARS = 500

THREAD_COMMAND_ALIASES = {
    "accept": {"command": "accept"},
    "accepted": {"command": "accept"},
    "escalate": {"command": "escalate"},
    "resolved": {"command": "set_status", "status": STATUS_RESOLVED},
    "resolve": {"command": "set_status", "status": STATUS_RESOLVED},
    "done": {"command": "set_status", "status": STATUS_RESOLVED},
    "in progress": {"command": "set_status", "status": STATUS_IN_PROGRESS},
    "in-progress": {"command": "set_status", "status": STATUS_IN_PROGRESS},
    "in_progress": {"command": "set_status", "status": STATUS_IN_PROGRESS},
    "closed": {"command": "close"},
}


class SlackPostError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def sanitize_slack_text(text: str | None) -> str:
    raw = "" if text is None else str(text)
    cleaned = MENTION_RE.sub("[mention-removed]", raw)
    cleaned = cleaned.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return cleaned


def _truncate(text: str, limit: int = MAX_DESCRIPTION_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _people_display(value: Any) -> str:
    if value is None or value == "":
        return "Unknown"
    return str(value)


def parse_thread_command(text: str | None) -> dict[str, str] | None:
    if not text:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    first = raw.splitlines()[0].strip()
    lowered = first.lower()
    if lowered in THREAD_COMMAND_ALIASES:
        return dict(THREAD_COMMAND_ALIASES[lowered])
    if lowered.startswith("reassign"):
        remainder = first.split(":", 1)
        team_text = remainder[1].strip() if len(remainder) == 2 else first[8:].strip(" :")
        team = resolve_team_name(team_text)
        if team is None:
            return {"command": "reassign", "team": team_text, "invalid": "1"}
        return {"command": "reassign", "team": team}
    return None


def is_bot_message(event: dict[str, Any], bot_user_id: str | None = None) -> bool:
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return True
    user = event.get("user")
    if bot_user_id and user == bot_user_id:
        return True
    return False


def build_action_blocks(incident_id: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "actions",
            "block_id": f"coord_actions_{incident_id}",
            "elements": [
                {
                    "type": "button",
                    "action_id": ACTION_ACCEPT,
                    "text": {"type": "plain_text", "text": "Accept"},
                    "value": incident_id,
                },
                {
                    "type": "button",
                    "action_id": ACTION_REASSIGN,
                    "text": {"type": "plain_text", "text": "Reassign"},
                    "value": incident_id,
                },
                {
                    "type": "button",
                    "action_id": ACTION_ESCALATE,
                    "text": {"type": "plain_text", "text": "Escalate"},
                    "value": incident_id,
                    "style": "danger",
                },
                {
                    "type": "button",
                    "action_id": ACTION_CLOSED,
                    "text": {"type": "plain_text", "text": "Closed"},
                    "value": incident_id,
                },
            ],
        }
    ]


def build_incident_blocks(
    *,
    incident_id: str,
    category: str,
    location: str | None,
    description: str | None,
    people_exposed: Any,
    risk_level: str | None,
    risk_explanation: str | None,
    recommended_action: str | None,
    assigned_team: str,
    duplicate_count: int = 1,
    status: str = "Assigned",
    include_actions: bool = True,
) -> list[dict[str, Any]]:
    loc = sanitize_slack_text(location) if location else "Unknown"
    desc = _truncate(sanitize_slack_text(description or "No description provided."))
    people = _people_display(people_exposed)
    level = sanitize_slack_text(risk_level or "Unknown")
    explanation = sanitize_slack_text(risk_explanation or "No explanation provided.")
    action = format_recommended_action(recommended_action)
    category_display = sanitize_slack_text(format_category_display(category))
    heading = "CRITICAL SAFETY INCIDENT" if (risk_level or "").lower() == "critical" else "Safety Incident"
    header = f"{heading}\nIncident: {sanitize_slack_text(incident_id)} | {category_display} | {loc}"
    fields = [
        f"*Risk:* {level}",
        f"*Status:* {sanitize_slack_text(status)}",
        f"*Assigned team:* {sanitize_slack_text(assigned_team)}",
        f"*People exposed:* {people}",
        f"*Recommended action:* {sanitize_slack_text(action)}",
    ]
    if duplicate_count > 1:
        fields.append(f"*Duplicate reports: {duplicate_count}*")
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": heading[:150]}},
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Description:*\n{desc}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(fields)}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Risk explanation:*\n{explanation}"}},
    ]
    if include_actions and status not in {STATUS_RESOLVED}:
        blocks.extend(build_action_blocks(incident_id))
    return blocks


def incident_fallback_text(blocks_context: dict[str, Any]) -> str:
    return (
        f"Safety incident {blocks_context.get('incident_id')} "
        f"({blocks_context.get('category')}) assigned to {blocks_context.get('assigned_team')}"
    )


class SlackHandler:
    """Thin Slack Web API wrapper. Inject ``client`` in tests."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str | None = None,
        destinations: dict[str, str] | None = None,
        bot_user_id: str | None = None,
    ) -> None:
        self._client = client
        self._token = token if token is not None else os.environ.get("SLACK_BOT_TOKEN", "").strip()
        self.destinations = destinations or {}
        self.bot_user_id = bot_user_id
        self.interactive_actions_supported = True

    def _sdk(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._token:
            raise SlackPostError("slack_channel_not_configured", "SLACK_BOT_TOKEN is not set")
        from slack_sdk.web.async_client import AsyncWebClient

        self._client = AsyncWebClient(token=self._token)
        return self._client

    def channel_for_team(self, team: str) -> str | None:
        return resolve_team_destination(team, self.destinations)

    async def post_incident_message(
        self,
        *,
        channel: str,
        blocks: list[dict[str, Any]],
        text: str,
    ) -> dict[str, Any]:
        return await self._call("chat_postMessage", channel=channel, blocks=blocks, text=text)

    async def post_thread_reply(self, *, channel: str, thread_ts: str, text: str) -> dict[str, Any]:
        return await self._call("chat_postMessage", channel=channel, thread_ts=thread_ts, text=text)

    async def update_incident_message(
        self,
        *,
        channel: str,
        ts: str,
        blocks: list[dict[str, Any]],
        text: str,
    ) -> dict[str, Any]:
        return await self._call("chat_update", channel=channel, ts=ts, blocks=blocks, text=text)

    async def _call(self, method: str, **kwargs: Any) -> dict[str, Any]:
        sdk = self._sdk()
        fn = getattr(sdk, method)
        try:
            result = fn(**kwargs)
            if hasattr(result, "__await__"):
                result = await result
        except Exception as exc:
            code = getattr(exc, "response", None)
            error = ""
            if code is not None and hasattr(code, "get"):
                error = str(code.get("error") or "")
            name = error or type(exc).__name__
            log.warning("slack_api_error method=%s error=%s", method, name)
            if name in PERMANENT_SLACK_ERRORS:
                raise SlackPostError(name, str(exc)) from exc
            if "Timeout" in type(exc).__name__ or "timeout" in str(exc).lower():
                raise SlackPostError("slack_post_failed", str(exc)) from exc
            raise SlackPostError("slack_post_failed", str(exc)) from exc
        data = result if isinstance(result, dict) else getattr(result, "data", None) or {}
        if data.get("ok") is False:
            err = str(data.get("error") or "slack_post_failed")
            log.warning("slack_api_error method=%s error=%s", method, err)
            raise SlackPostError(err, err)
        return {
            "ok": True,
            "ts": data.get("ts") or kwargs.get("ts"),
            "channel": data.get("channel") or kwargs.get("channel"),
            "message": data.get("message") or {},
        }


IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg"})


def extract_slack_file(event: dict[str, Any]) -> dict[str, Any] | None:
    files = event.get("files") or []
    if not files or not isinstance(files, list):
        file = event.get("file")
        files = [file] if isinstance(file, dict) else []
    if not files or not isinstance(files[0], dict):
        return None
    item = files[0]
    return {
        "id": item.get("id"),
        "name": item.get("name") or item.get("title"),
        "mimetype": item.get("mimetype") or item.get("filetype"),
        "url_private": item.get("url_private_download") or item.get("url_private"),
        "user": event.get("user") or item.get("user"),
        "thread_ts": event.get("thread_ts") or event.get("ts"),
        "channel": event.get("channel") or event.get("channel_id"),
        "event_id": event.get("event_id") or item.get("id"),
    }


def extract_action(payload: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (action_id, incident_id, selected_team)."""
    actions = payload.get("actions") or []
    if not actions or not isinstance(actions, list):
        return None, None, None
    action = actions[0] if isinstance(actions[0], dict) else {}
    action_id = action.get("action_id")
    incident_id = action.get("value") or (payload.get("message") or {}).get("metadata", {}).get(
        "event_payload", {}
    ).get("incident_id")
    selected = None
    option = action.get("selected_option")
    if isinstance(option, dict):
        selected = option.get("value")
    return action_id, incident_id, selected
