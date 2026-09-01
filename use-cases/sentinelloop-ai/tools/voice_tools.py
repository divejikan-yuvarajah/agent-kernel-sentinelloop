"""Voice-note transcription for worker safety reports.

Telegram voice notes arrive as ogg/opus. WhatsApp Cloud API voice notes are
``type=audio`` with ``audio.voice=true`` (Prompt 0 / Meta payload). OpenRouter
accepts those formats directly — this module does not convert codecs.

Never fabricates a transcript. Callers receive controlled errors and may ask
the worker for text instead of inventing speech.

Cost and budget checks live in ``tools.model_router`` so audio spend shares
``OPENROUTER_BUDGET_CEILING_USD`` with text and vision.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

log = logging.getLogger("sentinelloop.voice")

SUPPORTED_FORMATS = frozenset({"ogg", "opus", "mp3", "wav", "m4a"})
SUPPORTED_LANGUAGE_HINTS = frozenset({"si", "ta", "en"})
MIME_TO_FORMAT = {
    "audio/ogg": "ogg",
    "audio/opus": "opus",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
    "audio/webm": "ogg",
}
MAX_AUDIO_BYTES = 10 * 1024 * 1024
LOW_CONFIDENCE_THRESHOLD = 0.55
BUDGET_BLOCK_REASON = "AI budget ceiling reached"
VOICE_RETRY_MESSAGE = (
    "I could not clearly understand the voice message.\nPlease repeat or send text."
)
VOICE_INVALID_MESSAGE = (
    "I could not read that voice message. Please send a short text description of the hazard."
)
VOICE_UNAVAILABLE_MESSAGE = (
    "I could not process the voice message right now. Please send a short text description of the hazard."
)
LANGUAGE_NAMES = {"si": "Sinhala", "ta": "Tamil", "en": "English"}


class TranscriptionResult(BaseModel):
    """Controlled transcription outcome. Mapping-compatible for dict-style tests."""

    model_config = ConfigDict(extra="ignore")

    text: str = ""
    detected_language: str | None = None
    language: str | None = None
    cost_usd: float = 0.0
    blocked: bool = False
    reason: str | None = None
    available: bool = False
    audio_format: str = "ogg"
    error: str | None = None
    transcription_confidence: float | None = None
    model: str | None = None
    latency_s: float | None = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


def language_display_name(code: str | None) -> str | None:
    if not code:
        return None
    key = str(code).strip().lower()
    return LANGUAGE_NAMES.get(key, code)


def audio_format_from_mime(mime_type: str | None, *, fallback: str = "ogg") -> str:
    if not mime_type:
        return fallback
    mime = str(mime_type).split(";")[0].strip().lower()
    return MIME_TO_FORMAT.get(mime, fallback)


def normalize_language_hint(language_hint: str | None) -> str | None:
    if not language_hint:
        return None
    hint = str(language_hint).strip().lower()
    if hint in SUPPORTED_LANGUAGE_HINTS:
        return hint
    return None


def is_supported_audio_format(audio_format: str | None) -> bool:
    return (audio_format or "").strip().lower() in SUPPORTED_FORMATS


def is_low_confidence(result: TranscriptionResult | dict[str, Any]) -> bool:
    if isinstance(result, TranscriptionResult):
        confidence = result.transcription_confidence
        blocked = result.blocked
        available = result.available
    else:
        confidence = result.get("transcription_confidence")
        blocked = bool(result.get("blocked"))
        available = bool(result.get("available"))
    if blocked or not available:
        return True
    if confidence is None:
        return False
    try:
        return float(confidence) < LOW_CONFIDENCE_THRESHOLD
    except (TypeError, ValueError):
        return False


def confidence_band(confidence: float | None) -> str | None:
    if confidence is None:
        return None
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return None
    if value >= 0.8:
        return "high"
    if value >= LOW_CONFIDENCE_THRESHOLD:
        return "medium"
    return "low"


def worker_voice_fallback_message(result: TranscriptionResult | None = None) -> str:
    if result is None:
        return VOICE_UNAVAILABLE_MESSAGE
    if result.error == "unsupported_format" or result.error == "invalid_audio":
        return VOICE_INVALID_MESSAGE
    if result.blocked:
        return VOICE_UNAVAILABLE_MESSAGE
    if is_low_confidence(result) or result.error in {"empty_transcript", "transcription_failed", "timeout"}:
        return VOICE_RETRY_MESSAGE
    return VOICE_UNAVAILABLE_MESSAGE


def _blocked(fmt: str, reason: str = BUDGET_BLOCK_REASON) -> TranscriptionResult:
    return TranscriptionResult(
        audio_format=fmt,
        blocked=True,
        reason=reason,
        error="budget_exceeded",
    )


def _decode_audio(audio_base64: str) -> bytes | None:
    try:
        raw = base64.b64decode(audio_base64, validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if raw else None


async def transcribe_voice_note(
    audio_base64: str = "",
    audio_format: str = "ogg",
    language_hint: str | None = None,
    *,
    audio_b64: str | None = None,
    duration_seconds: float | None = None,
    call_model_fn: Any | None = None,
    router: Any | None = None,
) -> TranscriptionResult:
    """Transcribe a base64 voice note. Never fabricates a transcript.

    Signature matches the product contract plus the existing Telegram keyword
    ``audio_b64`` / ``call_model_fn`` injection used by tests.
    """
    payload = audio_b64 if audio_b64 else audio_base64
    fmt = (audio_format or "ogg").strip().lower() or "ogg"
    hint = normalize_language_hint(language_hint)

    if not payload:
        return TranscriptionResult(audio_format=fmt, error="empty_audio")
    if not is_supported_audio_format(fmt):
        log.warning("voice_transcription_blocked reason=unsupported_format format=%s", fmt)
        return TranscriptionResult(audio_format=fmt, error="unsupported_format")

    raw = _decode_audio(payload)
    if not raw:
        return TranscriptionResult(audio_format=fmt, error="invalid_audio")
    if len(raw) > MAX_AUDIO_BYTES:
        return TranscriptionResult(audio_format=fmt, error="invalid_audio", reason="audio_too_large")

    if call_model_fn is not None:
        return await _via_injected(
            call_model_fn,
            payload,
            fmt=fmt,
            duration_seconds=duration_seconds,
            language_hint=hint,
        )

    from tools.model_router import ModelRouterAuthError, ModelRouterConfigError, ModelRouterError, get_router

    try:
        gateway = router or await get_router()
    except (ModelRouterConfigError, ModelRouterError) as exc:
        log.warning("voice_transcription_unavailable reason=%s", type(exc).__name__)
        return TranscriptionResult(audio_format=fmt, error="transcription_unavailable")

    try:
        result = await gateway.transcribe_audio(
            audio_base64=payload,
            audio_format=fmt,
            language_hint=hint,
            duration_seconds=duration_seconds,
        )
    except ModelRouterAuthError:
        log.warning("voice_transcription_unavailable reason=auth")
        return TranscriptionResult(audio_format=fmt, error="transcription_unavailable")
    except Exception:
        log.warning("telegram_voice_transcribed available=false reason=transcriber_failed")
        return TranscriptionResult(audio_format=fmt, error="transcription_failed")
    return result


async def _via_injected(
    call_model_fn: Any,
    payload: str,
    *,
    fmt: str,
    duration_seconds: float | None,
    language_hint: str | None,
) -> TranscriptionResult:
    try:
        result = call_model_fn(
            payload,
            audio_format=fmt,
            duration_seconds=duration_seconds,
            language_hint=language_hint,
        )
        if hasattr(result, "__await__"):
            result = await result
    except Exception:
        log.warning("telegram_voice_transcribed available=false reason=transcriber_failed")
        return TranscriptionResult(audio_format=fmt, error="transcription_failed")
    return _parse_transcriber_payload(result, fmt=fmt)


def _parse_transcriber_payload(result: Any, *, fmt: str) -> TranscriptionResult:
    text = ""
    language = None
    cost = 0.0
    confidence = None
    model = None
    blocked = False
    reason = None
    error = None
    if isinstance(result, TranscriptionResult):
        return result
    if isinstance(result, str):
        text = result.strip()
    elif isinstance(result, dict):
        if result.get("blocked"):
            blocked = True
            reason = str(result.get("reason") or BUDGET_BLOCK_REASON)
            error = "budget_exceeded"
        text = str(result.get("text") or result.get("transcript") or "").strip()
        language = result.get("detected_language") or result.get("language")
        try:
            cost = float(result.get("cost_usd") or 0)
        except (TypeError, ValueError):
            cost = 0.0
        try:
            raw_conf = result.get("transcription_confidence")
            if raw_conf is None:
                raw_conf = result.get("confidence")
            confidence = float(raw_conf) if raw_conf is not None else None
        except (TypeError, ValueError):
            confidence = None
        model = result.get("model")
        error = result.get("error") if isinstance(result.get("error"), str) else error
    elif result is not None:
        text = str(getattr(result, "text", result) or "").strip()
        language = getattr(result, "language", None) or getattr(result, "detected_language", None)
    lang = str(language).strip().lower() if language else None
    if lang and lang not in SUPPORTED_LANGUAGE_HINTS and len(lang) > 8:
        lang = None
    if blocked:
        return _blocked(fmt, reason or BUDGET_BLOCK_REASON)
    if not text:
        return TranscriptionResult(
            audio_format=fmt,
            language=lang,
            detected_language=lang,
            error=error or "empty_transcript",
            transcription_confidence=confidence,
            model=str(model) if model else None,
            cost_usd=cost,
        )
    log.info("telegram_voice_transcribed available=true format=%s", fmt)
    return TranscriptionResult(
        text=text,
        language=lang,
        detected_language=lang,
        available=True,
        audio_format=fmt,
        cost_usd=cost,
        transcription_confidence=confidence,
        model=str(model) if model else None,
    )
