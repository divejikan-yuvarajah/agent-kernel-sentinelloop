"""Channel-neutral inbound worker message types.

Telegram is the only worker transport. These models are the orchestrator
contract; they do not call the Telegram Bot API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

ACTION_YES = "verification_yes"
ACTION_STILL_EXISTS = "verification_still_exists"
ACTION_UNSURE = "verification_unsure"

UNSUPPORTED_WORKER_REPLY = (
    "I can take a workplace hazard report as text or a photo. Please send a short description or an image."
)


class InboundMedia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    media_id: str | None = None
    mime_type: str | None = None
    filename: str | None = None
    provider_reference: str | None = None
    sha256: str | None = None
    content: bytes | None = None
    size_bytes: int | None = None


class NormalizedInboundMessage(BaseModel):
    """Normalized worker message. Downstream agents should use this."""

    model_config = ConfigDict(extra="ignore")

    provider_message_id: str
    sender_id: str
    message_type: str
    text: str | None = None
    caption: str | None = None
    media: InboundMedia | None = None
    reply_to_message_id: str | None = None
    received_at: datetime | None = None
    interactive_action_id: str | None = None
    interactive_title: str | None = None
    supported: bool = True
    raw_timestamp: str | None = None
    input_channel: str = "telegram"
    emergency_bypass: bool = False
    voice_used: bool = False
    audio_format: str | None = None
    transcription_available: bool = False
    media_unavailable: bool = False
    chat_id: str | None = None
    telegram_user_id: str | None = None
    username: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    language_code: str | None = None
    voice_duration_seconds: float | None = None
    audio_used: bool = False
    input_method: str | None = None
    detected_language: str | None = None
    transcription_cost: float | None = None
    transcription_confidence: float | None = None
    transcription_latency_s: float | None = None


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


def extract_callback_action(data: str | None) -> dict[str, Any] | None:
    parsed = parse_action_id(data)
    if parsed is None and not data:
        return None
    return parsed
