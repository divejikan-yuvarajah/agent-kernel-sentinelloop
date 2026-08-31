"""WhatsApp Cloud API transport for SentinelLoop inbound worker reports.

Owns webhook verification, message normalization, media retrieval, and
worker-facing sends. Incident business logic lives in the orchestrator.

Inbound Events API remains ``GET/POST /whatsapp/webhook`` via a subclass of
``AgentWhatsAppRequestHandler`` (Prompt 0 / SPEC). Outbound Graph calls reuse
``integrations.whatsapp.WhatsAppHandler``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from integrations.whatsapp import WhatsAppHandler, WhatsAppSendError, extract_interactive_reply, parse_action_id

log = logging.getLogger("sentinelloop.whatsapp")

SUPPORTED_TYPES = frozenset({"text", "image", "interactive"})
UNSUPPORTED_TYPES = frozenset(
    {"audio", "video", "sticker", "document", "location", "reaction", "contacts", "unknown", "button", "order"}
)
ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg"})
DEFAULT_MAX_MEDIA_BYTES = 16 * 1024 * 1024
UNSUPPORTED_WORKER_REPLY = (
    "I can take a workplace hazard report as text or a photo. Please send a short description or an image."
)


class WhatsAppMedia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media_id: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    provider_reference: str | None = None
    sha256: str | None = None
    content: bytes | None = None
    size_bytes: int | None = None


class NormalizedWhatsAppMessage(BaseModel):
    """Provider-neutral inbound message. Downstream agents should use this."""

    model_config = ConfigDict(extra="ignore")

    provider_message_id: str
    sender_id: str
    message_type: str
    text: str | None = None
    caption: str | None = None
    media: WhatsAppMedia | None = None
    reply_to_message_id: str | None = None
    received_at: datetime | None = None
    interactive_action_id: str | None = None
    interactive_title: str | None = None
    supported: bool = True
    raw_timestamp: str | None = None


class ResolvedMedia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media_id: str
    mime_type: str | None = None
    content: bytes = b""
    size_bytes: int = 0
    error: str | None = None


def verify_webhook_challenge(
    mode: str | None, token: str | None, challenge: str | None, expected_token: str
) -> str | None:
    """Meta GET verification. Returns the challenge string or None."""
    if mode == "subscribe" and token and expected_token and token == expected_token and challenge:
        return challenge
    return None


def verify_webhook_request(payload: bytes, signature: str | None, app_secret: str | None) -> bool:
    """Validate ``X-Hub-Signature-256`` using the same HMAC as Agent Kernel."""
    if not app_secret:
        return True
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    received = signature[7:]
    return hmac.compare_digest(expected, received)


def extract_reply_context(message: dict[str, Any] | None) -> str | None:
    if not isinstance(message, dict):
        return None
    context = message.get("context") or {}
    if not isinstance(context, dict):
        return None
    ident = context.get("id") or context.get("message_id")
    return str(ident) if ident else None


def _parse_received_at(message: dict[str, Any]) -> datetime | None:
    raw = message.get("timestamp")
    if raw is None:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _safe_mime(value: str | None) -> str | None:
    if not value:
        return None
    mime = str(value).split(";")[0].strip().lower()
    return mime or None


def normalize_incoming_message(
    message: dict[str, Any] | None,
    value: dict[str, Any] | None = None,
    *,
    received_at: datetime | None = None,
) -> NormalizedWhatsAppMessage | None:
    """Turn a Meta Cloud API message object into a normalized envelope."""
    del value  # contacts metadata is not trusted for sender identity
    if not isinstance(message, dict):
        return None
    provider_message_id = message.get("id")
    sender_id = message.get("from")
    if not provider_message_id or not sender_id:
        log.warning("whatsapp_inbound_malformed reason=missing_id_or_from")
        return None
    message_type = str(message.get("type") or "unknown").strip().lower() or "unknown"
    text: str | None = None
    caption: str | None = None
    media: WhatsAppMedia | None = None
    interactive_action_id: str | None = None
    interactive_title: str | None = None
    supported = message_type in SUPPORTED_TYPES

    if message_type == "text":
        body = (message.get("text") or {}).get("body") if isinstance(message.get("text"), dict) else None
        text = str(body).strip() if body else None
    elif message_type == "image":
        image_raw = message.get("image")
        image: dict[str, Any] = image_raw if isinstance(image_raw, dict) else {}
        caption_raw = image.get("caption")
        caption = str(caption_raw).strip() if caption_raw else None
        text = caption
        media_id = image.get("id")
        mime = _safe_mime(image.get("mime_type"))
        sha = image.get("sha256")
        media = WhatsAppMedia(
            media_id=str(media_id) if media_id else None,
            mime_type=mime,
            filename=None,
            provider_reference=str(media_id) if media_id else None,
            sha256=str(sha) if sha else None,
        )
    elif message_type == "interactive":
        parsed = extract_interactive_reply(message) or {}
        interactive_action_id = parsed.get("action") or parsed.get("id")
        if parsed.get("incident_id") and parsed.get("action"):
            interactive_action_id = f"{parsed['action']}:{parsed['incident_id']}:{parsed.get('cycle', '')}".rstrip(":")
        interactive_title = parsed.get("title")
        text = interactive_title
        if not interactive_action_id:
            interactive_raw = message.get("interactive")
            interactive: dict[str, Any] = interactive_raw if isinstance(interactive_raw, dict) else {}
            reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
            if isinstance(reply, dict):
                interactive_action_id = str(reply.get("id") or "") or None
                interactive_title = str(reply.get("title") or "") or interactive_title
                text = interactive_title or text
    else:
        supported = False

    return NormalizedWhatsAppMessage(
        provider_message_id=str(provider_message_id),
        sender_id=str(sender_id),
        message_type=message_type,
        text=text,
        caption=caption,
        media=media,
        reply_to_message_id=extract_reply_context(message),
        received_at=received_at or _parse_received_at(message),
        interactive_action_id=interactive_action_id,
        interactive_title=interactive_title,
        supported=supported,
        raw_timestamp=str(message["timestamp"]) if message.get("timestamp") is not None else None,
    )


def _normalize_send_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("id"):
        return result
    messages = result.get("messages")
    if not isinstance(messages, list):
        raw = result.get("raw")
        messages = raw.get("messages") if isinstance(raw, dict) else None
    message_id = None
    if isinstance(messages, list) and messages and isinstance(messages[0], dict):
        message_id = messages[0].get("id")
    out = dict(result)
    out.setdefault("ok", True)
    if message_id:
        out["id"] = message_id
    return out


class WhatsAppCloudTransport(WhatsAppHandler):
    """Outbound Cloud API plus secure inbound media download."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str | None = None,
        phone_number_id: str | None = None,
        api_version: str | None = None,
        media_client: Any | None = None,
        max_media_bytes: int | None = None,
    ) -> None:
        super().__init__(client, token=token, phone_number_id=phone_number_id, api_version=api_version)
        self._media_client = media_client
        self._max_media_bytes = max_media_bytes if max_media_bytes is not None else DEFAULT_MAX_MEDIA_BYTES

    def _graph_base(self) -> tuple[str, str]:
        token, _phone, version = self._credentials()
        return token, f"https://graph.facebook.com/{version}"

    async def send_text_message(self, to: str, text: str, *, reply_to_message_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        if reply_to_message_id:
            payload["context"] = {"message_id": reply_to_message_id}
        return _normalize_send_result(await self._post(payload))

    async def send_interactive_message(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
    ) -> dict[str, Any]:
        return await self.send_verification_prompt(to, body, buttons)

    async def send_clarification(
        self, to: str, question: str, *, reply_to_message_id: str | None = None
    ) -> dict[str, Any]:
        return await self.send_text_message(to, question, reply_to_message_id=reply_to_message_id)

    async def send_guidance(self, to: str, text: str, *, reply_to_message_id: str | None = None) -> dict[str, Any]:
        return await self.send_text_message(to, text, reply_to_message_id=reply_to_message_id)

    async def get_media_info(self, media_id: str) -> dict[str, Any]:
        if self._media_client is not None:
            result = self._media_client("info", media_id)
            if hasattr(result, "__await__"):
                result = await result
            return result if isinstance(result, dict) else {}
        token, base = self._graph_base()
        if not token:
            raise WhatsAppSendError("whatsapp_not_configured", "WhatsApp credentials are not set")
        url = f"{base}/{media_id}"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {}

    async def resolve_inbound_media(self, media: WhatsAppMedia | dict[str, Any] | None) -> ResolvedMedia | None:
        """Download bytes via Graph media id. Never fetch arbitrary worker-supplied URLs."""
        if media is None:
            return None
        if isinstance(media, dict):
            media = WhatsAppMedia.model_validate(media)
        media_id = (media.media_id or media.provider_reference or "").strip()
        if not media_id:
            return None
        if media.content:
            mime = _safe_mime(media.mime_type)
            if mime and mime not in ALLOWED_IMAGE_TYPES and not mime.startswith("image/"):
                return ResolvedMedia(media_id=media_id, mime_type=mime, error="unsupported_media_type")
            if len(media.content) > self._max_media_bytes:
                return ResolvedMedia(media_id=media_id, mime_type=mime, error="media_too_large")
            return ResolvedMedia(
                media_id=media_id,
                mime_type=mime,
                content=media.content,
                size_bytes=len(media.content),
            )
        try:
            if self._media_client is not None:
                result = self._media_client("download", media_id)
                if hasattr(result, "__await__"):
                    result = await result
                if not isinstance(result, dict):
                    return ResolvedMedia(media_id=media_id, error="media_retrieval_failed")
                content = result.get("content") or b""
                mime = _safe_mime(result.get("mime_type") or media.mime_type)
                if isinstance(content, str):
                    content = content.encode("utf-8")
            else:
                info = await self.get_media_info(media_id)
                mime = _safe_mime(info.get("mime_type") or media.mime_type)
                size = info.get("file_size")
                try:
                    size_n = int(size) if size is not None else 0
                except (TypeError, ValueError):
                    size_n = 0
                if size_n and size_n > self._max_media_bytes:
                    return ResolvedMedia(media_id=media_id, mime_type=mime, error="media_too_large")
                media_url = info.get("url")
                if not media_url or not str(media_url).startswith("https://"):
                    return ResolvedMedia(media_id=media_id, mime_type=mime, error="media_retrieval_failed")
                token, _base = self._graph_base()
                headers = {"Authorization": f"Bearer {token}"}
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.get(str(media_url), headers=headers)
                    response.raise_for_status()
                    content = response.content
            if mime and mime not in ALLOWED_IMAGE_TYPES and not mime.startswith("image/"):
                return ResolvedMedia(media_id=media_id, mime_type=mime, error="unsupported_media_type")
            if len(content) > self._max_media_bytes:
                return ResolvedMedia(media_id=media_id, mime_type=mime, error="media_too_large")
            return ResolvedMedia(media_id=media_id, mime_type=mime, content=content, size_bytes=len(content))
        except Exception:
            log.warning("whatsapp_media_retrieval_failed media_id=%s", media_id)
            return ResolvedMedia(media_id=media_id, error="media_retrieval_failed")


try:
    from agentkernel.whatsapp import AgentWhatsAppRequestHandler as _KernelWhatsAppHandler
except Exception:  # pragma: no cover - tests without WhatsApp extra
    _KernelWhatsAppHandler = object  # type: ignore[misc,assignment]


class SentinelLoopWhatsAppHandler(_KernelWhatsAppHandler):  # type: ignore[misc]
    """Registered with ``RESTAPI.run`` the same way as other Agent Kernel use cases.

    GET verification and HMAC checks stay on ``AgentWhatsAppRequestHandler``.
    ``_handle_message`` runs SentinelLoop orchestration instead of ``AgentService.run``.
    """

    def __init__(
        self,
        *,
        orchestrator: Any | None = None,
        transport: WhatsAppCloudTransport | None = None,
        skip_kernel_init: bool = False,
    ) -> None:
        if not skip_kernel_init and _KernelWhatsAppHandler is not object:
            super().__init__()
        else:
            self._log = log
        self._transport = transport or WhatsAppCloudTransport()
        self._orchestrator = orchestrator

    async def _handle_message(self, message: dict, value: dict):
        return await self.handle_incoming_webhook_message(message, value)

    async def handle_incoming_webhook(self, message: dict[str, Any], value: dict[str, Any] | None = None) -> Any:
        return await self.handle_incoming_webhook_message(message, value)

    async def handle_incoming_webhook_message(
        self, message: dict[str, Any], value: dict[str, Any] | None = None
    ) -> Any:
        normalized = normalize_incoming_message(message, value)
        if normalized is None:
            return None
        log.info("whatsapp_inbound_received type=%s", normalized.message_type)
        if not normalized.supported:
            log.info("whatsapp_unsupported_type type=%s", normalized.message_type)
            try:
                await self._transport.send_text_message(normalized.sender_id, UNSUPPORTED_WORKER_REPLY)
            except WhatsAppSendError:
                log.warning("whatsapp_unsupported_ack_failed")
            if self._orchestrator is not None:
                return await self._orchestrator.process_incoming_whatsapp_message(normalized)
            return None
        if normalized.media and normalized.media.media_id:
            resolved = await self._transport.resolve_inbound_media(normalized.media)
            if resolved is not None and resolved.content:
                normalized.media.content = resolved.content
                normalized.media.mime_type = resolved.mime_type or normalized.media.mime_type
                normalized.media.size_bytes = resolved.size_bytes
            elif resolved is not None and resolved.error:
                log.warning("whatsapp_media_skipped reason=%s", resolved.error)
        orchestrator = self._orchestrator
        if orchestrator is None:
            from integrations.incident_orchestrator import get_incident_orchestrator

            orchestrator = get_incident_orchestrator()
        return await orchestrator.process_incoming_whatsapp_message(normalized)
