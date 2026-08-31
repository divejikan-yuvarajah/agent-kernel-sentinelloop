"""Voice-note transcription for worker reports.

Telegram voice notes arrive as ogg/opus. OpenRouter accepts that format
directly — this module does not convert codecs.

Returns an empty transcript on failure so callers can ask for text instead
of inventing speech.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

log = logging.getLogger("sentinelloop.voice")


class TranscriptionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = ""
    language: str | None = None
    available: bool = False
    audio_format: str = "ogg"
    error: str | None = None


async def transcribe_voice_note(
    audio_b64: str,
    *,
    audio_format: str = "ogg",
    duration_seconds: float | None = None,
    call_model_fn: Any | None = None,
) -> TranscriptionResult:
    """Transcribe a base64 voice note. Never fabricates a transcript."""
    fmt = (audio_format or "ogg").strip().lower() or "ogg"
    if not audio_b64:
        return TranscriptionResult(audio_format=fmt, error="empty_audio")
    if call_model_fn is None:
        log.warning("telegram_voice_transcribed available=false reason=no_transcriber")
        return TranscriptionResult(audio_format=fmt, error="transcription_unavailable")
    try:
        result = call_model_fn(
            audio_b64,
            audio_format=fmt,
            duration_seconds=duration_seconds,
        )
        if hasattr(result, "__await__"):
            result = await result
    except Exception:
        log.warning("telegram_voice_transcribed available=false reason=transcriber_failed")
        return TranscriptionResult(audio_format=fmt, error="transcription_failed")
    text = ""
    language = None
    if isinstance(result, str):
        text = result.strip()
    elif isinstance(result, dict):
        text = str(result.get("text") or result.get("transcript") or "").strip()
        language = result.get("language")
    elif result is not None:
        text = str(getattr(result, "text", result) or "").strip()
        language = getattr(result, "language", None)
    if not text:
        return TranscriptionResult(audio_format=fmt, language=language, error="empty_transcript")
    log.info("telegram_voice_transcribed available=true format=%s", fmt)
    return TranscriptionResult(
        text=text,
        language=str(language) if language else None,
        available=True,
        audio_format=fmt,
    )
