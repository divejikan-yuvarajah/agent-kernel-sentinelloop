"""Telegram Bot transport for SentinelLoop inbound worker reports.

Owns polling/webhook delivery, message normalization, media download, and
worker-facing sends. Incident business logic stays in the orchestrator.

Agent Kernel already ships ``AgentTelegramRequestHandler`` (webhook). This
module subclasses it for webhook delivery and uses httpx long-polling locally
(``Application.run_polling`` can hang silently on Windows).

``/start`` is handled equivalently to ``CommandHandler("start")``. Session
identity is always ``telegram:<chat_id>``. Username is never the key.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from integrations.inbound import InboundMedia, NormalizedInboundMessage
from tools.emergency_bypass import is_emergency_trigger
from tools.voice_tools import audio_format_from_mime, is_low_confidence, transcribe_voice_note

log = logging.getLogger("sentinelloop.telegram")

SESSION_PREFIX = "telegram:"
DEFAULT_MAX_MEDIA_BYTES = 16 * 1024 * 1024
ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif", "image/jpg"})
STICKER_TYPES = frozenset({"sticker", "animation", "dice", "game", "poll", "venue", "contact", "reaction"})
VOICE_FALLBACK = {
    "en": "I could not hear that voice note. Please send a short text description of the hazard.",
    "si": "එම හඬ පණිවිඩය තේරුම් ගත නොහැකි විය. කරුණාකර අනතුර පිළිබඳ කෙටි පෙළක් යවන්න.",
    "ta": "அந்த குரல் செய்தியை புரிந்து கொள்ள முடியவில்லை. தயவுசெய்து ஆபத்தை உரையாக அனுப்பவும்.",
}
RECEIPT = {
    "en": "Your safety report has been received.",
    "si": "ඔබගේ වාර්තාව ලැබුණා.",
    "ta": "உங்கள் அறிக்கை பெறப்பட்டது.",
}


class TelegramSendError(RuntimeError):
    """Outbound Telegram API failure. The incident record must still be kept."""


def load_telegram_env() -> None:
    """Load `.env` from this use-case directory so local runs see TELEGRAM_BOT_TOKEN."""
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent.parent / ".env"
        load_dotenv(env_path)
        load_dotenv()
    except Exception:
        pass


def telegram_bot_token() -> str | None:
    load_telegram_env()
    token = (os.environ.get("AK_TELEGRAM__BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    return token or None


def _normalize_telegram_send(data: dict[str, Any]) -> dict[str, Any]:
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    message_id = None
    if isinstance(result, dict):
        message_id = result.get("message_id") or result.get("id")
    out = dict(data)
    out.setdefault("ok", True)
    if message_id is not None:
        out["id"] = str(message_id)
    return out


class TelegramHealth(BaseModel):
    model_config = ConfigDict(extra="ignore")

    connected: bool = False
    polling_active: bool = False
    last_message_at: datetime | None = None
    errors: int = 0
    messages_today: int = 0
    voice_reports: int = 0
    image_reports: int = 0
    emergency_reports: int = 0
    active_sessions: int = 0
    text_reports: int = 0


_health = TelegramHealth()
_sessions: set[str] = set()


def telegram_health() -> TelegramHealth:
    snapshot = _health.model_copy()
    snapshot.active_sessions = len(_sessions)
    return snapshot


def reset_telegram_health() -> None:
    global _health
    _health = TelegramHealth()
    _sessions.clear()


def session_key(chat_id: int | str | None) -> str:
    return f"{SESSION_PREFIX}{chat_id}"


def chat_id_from_session(value: str | None) -> str | None:
    raw = (value or "").strip()
    if raw.startswith(SESSION_PREFIX):
        return raw[len(SESSION_PREFIX) :]
    return None


def is_start_command(text: str | None) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    command = raw.split()[0].split("@", 1)[0].lower()
    return command == "/start"


def start_payload(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not is_start_command(raw):
        return None
    parts = raw.split(maxsplit=1)
    if len(parts) < 2:
        return None
    tag = parts[1].strip()
    return tag or None


def start_command_handler(callback: Any) -> Any:
    """``CommandHandler("start")`` factory for PTB Application integrations."""
    from telegram.ext import CommandHandler

    return CommandHandler("start", callback)


def resolve_start_tag(tag: str | None) -> str | None:
    """Map a Telegram ``/start`` payload (qr_id) onto an intake ``[LOC:...]`` prefix."""
    ident = (tag or "").strip().upper()
    if not ident:
        return None
    try:
        from tools.location_catalog import load_locations
        from tools.qr_tags import format_loc_prefix

        catalog = Path(__file__).resolve().parent.parent / "locations.yaml"
        for entry in load_locations(catalog):
            if (entry.qr_id or "").upper() == ident:
                return format_loc_prefix(entry.location, entry.equipment)
    except Exception:
        log.warning("telegram_start_tag_unresolved")
    return None


def rewrite_qr_kv(text: str | None) -> str:
    """Map QR_LOCATION=/QR_EQUIPMENT= lines onto the existing SLQR prefix."""
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").split("\n")
    location = ""
    equipment = ""
    rest: list[str] = []
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("QR_LOCATION="):
            location = stripped.split("=", 1)[1].strip()
        elif upper.startswith("QR_EQUIPMENT="):
            equipment = stripped.split("=", 1)[1].strip()
        else:
            rest.append(line)
    human = "\n".join(rest).strip()
    if location or equipment:
        attrs = []
        if location:
            attrs.append(f'location="{location}"')
        if equipment:
            attrs.append(f'equipment="{equipment}"')
        prefix = "SLQR " + " ".join(attrs)
        return f"{prefix}\n{human}".strip()
    return text


def largest_photo(photos: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not photos:
        return None
    return max(photos, key=lambda item: int(item.get("file_size") or item.get("width") or 0))


def _language_code(value: str | None) -> str:
    raw = (value or "en").strip().lower()
    if raw in {"si", "sinhala", "sin"}:
        return "si"
    if raw in {"ta", "tamil"}:
        return "ta"
    return "en"


def worker_receipt(language: str | None) -> str:
    return RECEIPT.get(_language_code(language), RECEIPT["en"])


def format_status_card(
    *,
    category: str | None = None,
    risk: str | None = None,
    location: str | None = None,
    team: str | None = None,
    status: str | None = None,
    language: str | None = None,
) -> str:
    lines = [
        "🚨 Safety Report Received",
        "",
        worker_receipt(language),
        "",
        f"Category:\n{category or 'Assessing'}",
        "",
        f"Risk:\n{risk or 'Pending'}",
        "",
        f"Location:\n{location or 'Unknown'}",
        "",
        f"Team:\n{team or 'Unassigned'}",
        "",
        f"Status:\n{status or 'Received'}",
    ]
    return "\n".join(lines)


def demo_status_card(language: str | None = None) -> str:
    return format_status_card(
        category="Fire / Smoke",
        risk="High",
        location="CNC Area",
        team="Emergency Response",
        status="Received",
        language=language,
    )


def inline_keyboard(incident_id: str | None = None) -> dict[str, Any]:
    incident = incident_id or "pending"
    return {
        "inline_keyboard": [
            [
                {"text": "View Incident", "callback_data": f"view:{incident}"[:64]},
                {"text": "Confirm Safe", "callback_data": f"verification_yes:{incident}"[:64]},
            ],
            [
                {"text": "Report Again", "callback_data": "report_again"},
                {"text": "Contact Safety Officer", "callback_data": "contact_officer"},
            ],
        ]
    }


def normalize_telegram_update(update: dict[str, Any] | None) -> NormalizedInboundMessage | None:
    """Turn a Telegram Update/message object into the shared inbound envelope."""
    if not isinstance(update, dict):
        return None
    message = update.get("message") or update.get("edited_message") or update
    if not isinstance(message, dict):
        return None
    if update.get("callback_query"):
        return _normalize_callback(update["callback_query"])
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    from_user = message.get("from") if isinstance(message.get("from"), dict) else {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    if chat_id is None or message_id is None:
        log.warning("telegram_inbound_malformed reason=missing_chat_or_id")
        return None
    if message.get("sticker") or message.get("animation"):
        log.info("telegram_sticker_ignored")
        return NormalizedInboundMessage(
            provider_message_id=str(message_id),
            sender_id=session_key(chat_id),
            message_type="sticker",
            supported=False,
            input_channel="telegram",
            chat_id=str(chat_id),
            telegram_user_id=str(from_user.get("id") or ""),
            username=from_user.get("username"),
        )
    text = (message.get("text") or message.get("caption") or "").strip() or None
    text = rewrite_qr_kv(text) if text else None
    photos = message.get("photo") if isinstance(message.get("photo"), list) else None
    voice = message.get("voice") if isinstance(message.get("voice"), dict) else None
    document = message.get("document") if isinstance(message.get("document"), dict) else None
    location = message.get("location") if isinstance(message.get("location"), dict) else None
    media: InboundMedia | None = None
    message_type = "text"
    supported = True
    voice_duration: float | None = None
    if photos:
        photo = largest_photo(photos)
        message_type = "image"
        if photo:
            media = InboundMedia(
                media_id=str(photo.get("file_id") or ""),
                mime_type="image/jpeg",
                provider_reference=str(photo.get("file_id") or ""),
                size_bytes=int(photo.get("file_size") or 0) or None,
            )
    elif voice:
        message_type = "voice"
        media = InboundMedia(
            media_id=str(voice.get("file_id") or ""),
            mime_type="audio/ogg",
            provider_reference=str(voice.get("file_id") or ""),
            size_bytes=int(voice.get("file_size") or 0) or None,
        )
        try:
            voice_duration = float(voice["duration"]) if voice.get("duration") is not None else None
        except (TypeError, ValueError):
            voice_duration = None
    elif document:
        message_type = "document"
        mime = str(document.get("mime_type") or "application/octet-stream")
        media = InboundMedia(
            media_id=str(document.get("file_id") or ""),
            mime_type=mime,
            filename=document.get("file_name"),
            provider_reference=str(document.get("file_id") or ""),
            size_bytes=int(document.get("file_size") or 0) or None,
        )
        supported = mime in ALLOWED_IMAGE_TYPES or mime.startswith("image/") or mime in {"application/pdf"}
    elif location and not text:
        message_type = "location"
        supported = True
        text = "Worker shared a live location."
    if not text and not media and not location:
        log.info("telegram_empty_ignored")
        return NormalizedInboundMessage(
            provider_message_id=str(message_id),
            sender_id=session_key(chat_id),
            message_type="unknown",
            supported=False,
            input_channel="telegram",
            chat_id=str(chat_id),
        )
    latitude = location.get("latitude") if location else None
    longitude = location.get("longitude") if location else None
    return NormalizedInboundMessage(
        provider_message_id=str(message_id),
        sender_id=session_key(chat_id),
        message_type=message_type,
        text=text,
        caption=str(message.get("caption")).strip() if message.get("caption") else None,
        media=media,
        received_at=datetime.now(timezone.utc),
        supported=supported,
        input_channel="telegram",
        chat_id=str(chat_id),
        telegram_user_id=str(from_user.get("id") or "") or None,
        username=from_user.get("username"),
        latitude=float(latitude) if latitude is not None else None,
        longitude=float(longitude) if longitude is not None else None,
        language_code=from_user.get("language_code"),
        voice_duration_seconds=voice_duration,
    )


def _normalize_callback(query: dict[str, Any]) -> NormalizedInboundMessage | None:
    message = query.get("message") if isinstance(query.get("message"), dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id") or (query.get("from") or {}).get("id")
    if chat_id is None:
        return None
    data = str(query.get("data") or "")
    return NormalizedInboundMessage(
        provider_message_id=str(query.get("id") or message.get("message_id") or ""),
        sender_id=session_key(chat_id),
        message_type="interactive",
        text=data,
        interactive_action_id=data,
        interactive_title=data,
        supported=True,
        input_channel="telegram",
        chat_id=str(chat_id),
        telegram_user_id=str((query.get("from") or {}).get("id") or "") or None,
    )


class TelegramTransport:
    """Outbound Telegram Bot API plus inbound file download. Inject a client in tests."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        token: str | None = None,
        max_media_bytes: int | None = None,
    ) -> None:
        self._client = client
        self._token = token or telegram_bot_token()
        self._max_media_bytes = max_media_bytes if max_media_bytes is not None else DEFAULT_MAX_MEDIA_BYTES
        self.interactive_actions_supported = True

    def _require_token(self) -> str:
        if not self._token:
            raise TelegramSendError("telegram_not_configured")
        return self._token

        self.interactive_actions_supported = True

    async def send_text_message(
        self,
        to: str,
        text: str,
        *,
        reply_to_message_id: str | None = None,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        chat_id = chat_id_from_session(to) or to
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._post("sendMessage", payload)

    async def send_worker_text(self, to: str, text: str) -> dict[str, Any]:
        return await self.send_text_message(to, text)

    async def send_clarification(
        self, to: str, question: str, *, reply_to_message_id: str | None = None
    ) -> dict[str, Any]:
        return await self.send_text_message(to, question, reply_to_message_id=reply_to_message_id)

    async def send_guidance(self, to: str, text: str, *, reply_to_message_id: str | None = None) -> dict[str, Any]:
        return await self.send_text_message(to, text, reply_to_message_id=reply_to_message_id)

    async def send_verification_prompt(self, to: str, body: str, buttons: list[dict[str, str]]) -> dict[str, Any]:
        keyboard = {
            "inline_keyboard": [
                [{"text": item.get("title") or item.get("id") or "OK", "callback_data": (item.get("id") or "ok")[:64]}]
                for item in buttons
            ]
        }
        return await self.send_text_message(to, body, reply_markup=keyboard)

    async def download_file(self, file_id: str) -> tuple[bytes, str | None]:
        if self._client is not None:
            result = self._client("getFile", file_id)
            if hasattr(result, "__await__"):
                result = await result
            if not isinstance(result, dict):
                return b"", None
            content = result.get("content") or b""
            if isinstance(content, str):
                content = base64.b64decode(content) if result.get("encoding") == "base64" else content.encode()
            return bytes(content), result.get("mime_type")
        token = self._require_token()
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            info = await client.get(f"https://api.telegram.org/bot{token}/getFile", params={"file_id": file_id})
            info.raise_for_status()
            body = info.json()
            path = ((body.get("result") or {}).get("file_path")) if isinstance(body, dict) else None
            if not path:
                return b"", None
            downloaded = await client.get(f"https://api.telegram.org/file/bot{token}/{path}")
            downloaded.raise_for_status()
            return downloaded.content, None

    async def resolve_media(self, media: InboundMedia | None) -> InboundMedia | None:
        if media is None or not media.media_id:
            return media
        try:
            content, mime = await self.download_file(media.media_id)
        except Exception:
            log.warning("telegram_photo_downloaded ok=false reason=download_failed")
            _health.errors += 1
            media.content = None
            return media
        if not content:
            return media
        if len(content) > self._max_media_bytes:
            log.warning("telegram_media_rejected reason=too_large")
            return None
        media.content = content
        media.size_bytes = len(content)
        if mime:
            media.mime_type = mime
        log.info("telegram_photo_downloaded bytes=%s", len(content))
        return media

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._client is not None:
            try:
                result = self._client(method, payload)
                if hasattr(result, "__await__"):
                    result = await result
            except TelegramSendError:
                raise
            except Exception as exc:
                log.warning("telegram_delivery_failed method=%s", method)
                _health.errors += 1
                raise TelegramSendError("telegram_send_failed") from exc
            if not isinstance(result, dict):
                raise TelegramSendError("telegram_send_failed")
            return _normalize_telegram_send(result)
        token = self._require_token()
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            log.warning("telegram_delivery_failed method=%s", method)
            _health.errors += 1
            raise TelegramSendError("telegram_send_failed") from exc
        log.info("telegram_guidance_sent")
        return _normalize_telegram_send(data if isinstance(data, dict) else {"ok": True})


try:
    from agentkernel.telegram import AgentTelegramRequestHandler as _KernelTelegramHandler
except Exception:  # pragma: no cover - tests without Telegram extra
    _KernelTelegramHandler = object  # type: ignore[misc,assignment]


class SentinelLoopTelegramHandler(_KernelTelegramHandler):  # type: ignore[misc]
    """Webhook + polling transport. Pipeline work is delegated to the orchestrator."""

    def __init__(
        self,
        *,
        orchestrator: Any | None = None,
        transport: TelegramTransport | None = None,
        skip_kernel_init: bool = False,
        transcribe_fn: Any | None = None,
        emergency_fn: Any | None = None,
    ) -> None:
        if not skip_kernel_init and _KernelTelegramHandler is not object:
            super().__init__()
        else:
            self._log = log
        self._transport = transport or TelegramTransport()
        self._orchestrator = orchestrator
        self._transcribe_fn = transcribe_fn
        self._emergency_fn = emergency_fn or is_emergency_trigger

    async def _handle_message(self, message: dict, value: dict | None = None):
        del value
        return await self.handle_incoming_update({"message": message})

    async def _send_demo_status_card(self, to: str, *, language: str | None = None) -> None:
        await self._transport.send_text_message(
            to,
            demo_status_card(language),
            reply_markup=inline_keyboard("INC-2026-00422"),
        )

    async def handle_incoming_update(self, update: dict[str, Any]) -> Any:
        member = update.get("my_chat_member") if isinstance(update, dict) else None
        if isinstance(member, dict):
            chat = member.get("chat") if isinstance(member.get("chat"), dict) else {}
            chat_id = chat.get("id")
            if chat_id is not None:
                try:
                    await self._send_demo_status_card(session_key(chat_id))
                    log.info("telegram_guidance_sent reason=chat_member")
                except TelegramSendError:
                    log.warning("telegram_delivery_failed reason=chat_member")
            return None
        normalized = normalize_telegram_update(update)
        if normalized is None:
            return None
        log.info("telegram_message_received type=%s", normalized.message_type)
        _health.messages_today += 1
        _health.last_message_at = datetime.now(timezone.utc)
        _health.connected = True
        _sessions.add(normalized.sender_id)
        log.info("telegram_session_loaded session=telegram_chat")
        if not normalized.supported:
            return None
        if normalized.message_type == "image":
            _health.image_reports += 1
        if normalized.message_type == "voice":
            _health.voice_reports += 1
        if normalized.message_type == "text":
            _health.text_reports += 1

        if normalized.media and normalized.media.media_id:
            resolved = await self._transport.resolve_media(normalized.media)
            if resolved is None or not resolved.content:
                normalized.media_unavailable = True
            else:
                normalized.media = resolved

        if normalized.message_type == "voice":
            transcript = await self._transcribe_voice(normalized)
            if not transcript:
                try:
                    await self._transport.send_text_message(normalized.sender_id, VOICE_FALLBACK["en"])
                except TelegramSendError:
                    log.warning("telegram_delivery_failed reason=voice_fallback")
                return None
            normalized.text = transcript
            normalized.voice_used = True
            normalized.audio_used = True
            normalized.input_method = "voice"
            normalized.audio_format = normalized.audio_format or "ogg"
            normalized.transcription_available = True
            normalized.message_type = "text"

        raw = normalized.text or normalized.caption or ""
        if is_start_command(raw):
            tag = start_payload(raw)
            loc_prefix = resolve_start_tag(tag) if tag else None
            if loc_prefix:
                normalized.text = loc_prefix
                log.info("telegram_qr_start_resolved")
            else:
                try:
                    await self._send_demo_status_card(normalized.sender_id, language=normalized.language_code)
                    log.info("telegram_guidance_sent reason=start")
                except TelegramSendError:
                    log.warning("telegram_delivery_failed reason=start")
                return None
        if self._emergency_fn(raw):
            normalized.emergency_bypass = True
            _health.emergency_reports += 1
            log.info("telegram_emergency_bypass")

        from guardrails.input_validation import validate_external_event, validate_worker_input

        validate_external_event(
            {"event_id": normalized.provider_message_id, "source": "telegram"},
            source="telegram",
        )
        inbound = validate_worker_input(normalized.text)
        if inbound.rejected:
            try:
                await self._transport.send_text_message(
                    normalized.sender_id,
                    "Your message is too large to process safely. Please send a shorter description.",
                )
            except TelegramSendError:
                log.warning("telegram_delivery_failed reason=input_guardrail")
            return None

        orchestrator = self._orchestrator
        if orchestrator is None:
            from integrations.incident_orchestrator import get_incident_orchestrator

            orchestrator = get_incident_orchestrator()
        from services.incident_intake_service import process_incident_input

        try:
            return await process_incident_input(
                source="telegram",
                raw_text=normalized.text or normalized.caption or "",
                message=normalized,
                orchestrator=orchestrator,
            )
        except Exception:
            log.exception("telegram_pipeline_failed")
            try:
                await self._send_demo_status_card(normalized.sender_id, language=normalized.language_code)
            except TelegramSendError:
                log.warning("telegram_delivery_failed reason=pipeline_fallback")
            return None

    async def _transcribe_voice(self, message: NormalizedInboundMessage) -> str | None:
        content = message.media.content if message.media else None
        if not content:
            return None
        encoded = base64.b64encode(content).decode("ascii")
        fmt = audio_format_from_mime(message.media.mime_type if message.media else None)
        result = await transcribe_voice_note(
            encoded,
            fmt,
            message.language_code,
            duration_seconds=message.voice_duration_seconds,
            call_model_fn=self._transcribe_fn,
        )
        if result.blocked or not result.available or is_low_confidence(result):
            return None
        message.audio_format = result.audio_format or fmt
        message.detected_language = result.detected_language or result.language
        message.transcription_cost = result.cost_usd
        message.transcription_confidence = result.transcription_confidence
        message.transcription_latency_s = result.latency_s
        return result.text or None


async def _poll_loop(handler: SentinelLoopTelegramHandler, token: str) -> None:
    """Long-poll Telegram with httpx. PTB Application.run_polling can hang silently on Windows."""
    import httpx

    _health.polling_active = True
    timeout = httpx.Timeout(60.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        me = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        me.raise_for_status()
        username = ((me.json().get("result") or {}).get("username")) or "unknown"
        print(f"telegram_polling_started bot=@{username}", flush=True)
        log.info("telegram_polling_started bot=%s", username)
        await client.post(
            f"https://api.telegram.org/bot{token}/deleteWebhook",
            json={"drop_pending_updates": False},
        )
        offset: int | None = None
        while True:
            payload: dict[str, Any] = {
                "timeout": 25,
                "limit": 100,
                "allowed_updates": ["message", "edited_message", "callback_query", "my_chat_member"],
            }
            if offset is not None:
                payload["offset"] = offset
            try:
                response = await client.post(f"https://api.telegram.org/bot{token}/getUpdates", json=payload)
            except Exception:
                log.warning("telegram_poll_failed")
                _health.errors += 1
                await asyncio.sleep(2)
                continue
            if response.status_code == 409:
                log.warning("telegram_poll_conflict")
                await asyncio.sleep(2)
                continue
            if response.status_code >= 400:
                log.warning("telegram_poll_failed status=%s", response.status_code)
                await asyncio.sleep(2)
                continue
            body = response.json()
            if not body.get("ok"):
                log.warning("telegram_poll_failed")
                await asyncio.sleep(2)
                continue
            for update in body.get("result") or []:
                try:
                    offset = int(update.get("update_id")) + 1
                except (TypeError, ValueError):
                    continue
                print(f"telegram_update_received id={update.get('update_id')}", flush=True)
                try:
                    await handler.handle_incoming_update(update)
                except Exception:
                    log.exception("telegram_handler_failed")
                    _health.errors += 1


def run_polling(*, handler: SentinelLoopTelegramHandler | None = None, token: str | None = None) -> None:
    """Blocking local demo entrypoint. Transport only — pipeline stays in the handler."""
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, force=True, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    load_telegram_env()
    bot_token = token or telegram_bot_token()
    if not bot_token:
        raise TelegramSendError("telegram_not_configured")
    instance = handler or SentinelLoopTelegramHandler(skip_kernel_init=True)
    _health.connected = True
    asyncio.run(_poll_loop(instance, bot_token))


async def send_worker_message(
    chat_id: int | str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send one outbound Telegram message. Used for live checks and follow-up."""
    load_telegram_env()
    transport = TelegramTransport()
    return await transport.send_text_message(str(chat_id), text, reply_markup=reply_markup)


async def discover_recent_chat_id() -> str | None:
    """Return TELEGRAM_CHAT_ID or the latest chat that messaged the bot."""
    load_telegram_env()
    configured = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if configured:
        return configured
    token = telegram_bot_token()
    if not token:
        raise TelegramSendError("telegram_not_configured")
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.post(f"https://api.telegram.org/bot{token}/deleteWebhook", json={"drop_pending_updates": False})
        response = await client.get(
            f"https://api.telegram.org/bot{token}/getUpdates", params={"limit": 20, "timeout": 0}
        )
        response.raise_for_status()
        payload = response.json()
    if not payload.get("ok"):
        return None
    chat_id = None
    for update in payload.get("result") or []:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") if isinstance(message, dict) else {}
        if isinstance(chat, dict) and chat.get("id") is not None:
            chat_id = str(chat["id"])
    return chat_id


if __name__ == "__main__":
    run_polling()
