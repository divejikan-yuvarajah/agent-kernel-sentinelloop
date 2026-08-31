"""Application-level WhatsApp Cloud API transport for worker verification.

Outbound messages use Graph API httpx (SPEC). Inbound Events API remains
AgentWhatsAppRequestHandler. Interactive reply buttons are application-layer.

Never hard-code access tokens.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

log = logging.getLogger("sentinelloop.whatsapp")

BUTTON_TITLE_MAX = 20
ACTION_YES = "verification_yes"
ACTION_STILL_EXISTS = "verification_still_exists"
ACTION_UNSURE = "verification_unsure"


class WhatsAppSendError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


def encode_action(action: str, incident_id: str, cycle: int) -> str:
    return f"{action}:{incident_id}:{cycle}"


def parse_action_id(action_id: str | None) -> dict[str, str] | None:
    if not action_id:
        return None
    parts = str(action_id).split(":")
    if not parts:
        return None
    command = parts[0]
    if command not in {ACTION_YES, ACTION_STILL_EXISTS, ACTION_UNSURE}:
        return None
    result = {"action": command}
    if len(parts) > 1 and parts[1]:
        result["incident_id"] = parts[1]
    if len(parts) > 2 and parts[2]:
        result["cycle"] = parts[2]
    return result


def extract_interactive_reply(message: dict[str, Any]) -> dict[str, str] | None:
    interactive = message.get("interactive") or {}
    if not isinstance(interactive, dict):
        return None
    reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
    if not isinstance(reply, dict):
        return None
    action_id = reply.get("id")
    title = reply.get("title")
    parsed = parse_action_id(str(action_id) if action_id else None)
    if parsed is None and not title:
        return None
    data = parsed or {}
    if title:
        data["title"] = str(title)
    return data or None


class WhatsAppHandler:
    """Thin Cloud API wrapper. Inject ``client`` in tests (async callable)."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str | None = None,
        phone_number_id: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self._client = client
        self._token = token
        self._phone_number_id = phone_number_id
        self._api_version = api_version
        self.interactive_actions_supported = True

    def _credentials(self) -> tuple[str, str, str]:
        token = (
            self._token
            if self._token is not None
            else (os.environ.get("AK_WHATSAPP__ACCESS_TOKEN") or os.environ.get("WHATSAPP_API_TOKEN") or "").strip()
        )
        phone = (
            self._phone_number_id
            if self._phone_number_id is not None
            else (
                os.environ.get("AK_WHATSAPP__PHONE_NUMBER_ID") or os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or ""
            ).strip()
        )
        version = (
            self._api_version
            if self._api_version is not None
            else (os.environ.get("AK_WHATSAPP__API_VERSION") or "v24.0").strip() or "v24.0"
        )
        return token, phone, version

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._client is not None:
            try:
                result = self._client(payload)
                if hasattr(result, "__await__"):
                    result = await result
            except Exception as exc:
                raise WhatsAppSendError("whatsapp_send_failed", str(exc)) from exc
            if not isinstance(result, dict):
                return {"ok": True}
            return result
        token, phone, version = self._credentials()
        if not token or not phone:
            raise WhatsAppSendError("whatsapp_not_configured", "WhatsApp credentials are not set")
        url = f"https://graph.facebook.com/{version}/{phone}/messages"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            log.warning("whatsapp_send_failed error=%s", type(exc).__name__)
            raise WhatsAppSendError("whatsapp_send_failed", str(exc)) from exc
        message_id = None
        messages = data.get("messages") if isinstance(data, dict) else None
        if isinstance(messages, list) and messages and isinstance(messages[0], dict):
            message_id = messages[0].get("id")
        return {"ok": True, "id": message_id, "raw": data}

    async def send_worker_text(self, to: str, text: str) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        return await self._post(payload)

    async def send_verification_prompt(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
    ) -> dict[str, Any]:
        elements = []
        for button in buttons[:3]:
            title = str(button.get("title") or "")[:BUTTON_TITLE_MAX]
            action_id = str(button.get("id") or "")[:256]
            if not title or not action_id:
                continue
            elements.append({"type": "reply", "reply": {"id": action_id, "title": title}})
        if not elements:
            return await self.send_worker_text(to, body)
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {"buttons": elements},
            },
        }
        return await self._post(payload)
