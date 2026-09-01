"""Text-to-speech for worker guidance replies.

Synthesizes spoken safety guidance through the shared OpenRouter model router
(``role_tts``). Never blocks text delivery — callers treat failure as
text-only fallback.

Audio bytes are returned in memory. Callers must delete any temporary files
they create. Raw voice content is not logged.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger("sentinelloop.voice_out")

SUPPORTED_LANGUAGES = frozenset({"en", "si", "ta", "english", "sinhala", "tamil"})
LANGUAGE_ALIASES = {
    "en": "en",
    "english": "en",
    "si": "si",
    "sinhala": "si",
    "ta": "ta",
    "tamil": "ta",
}
LANGUAGE_NAMES = {"en": "English", "si": "Sinhala", "ta": "Tamil"}

VOICE_PREF_PHRASES = (
    "send voice",
    "i prefer audio",
    "prefer audio",
    "speak to me",
    "voice reply",
    "send audio",
    "audio please",
    "voice please",
    "reply with voice",
)

_PREF_LOCK = threading.Lock()
_PREF_PATH = Path(__file__).resolve().parents[1] / ".runtime" / "voice_preferences.json"


class SpeechResult(BaseModel):
    """Controlled TTS outcome. Mapping-compatible for tests."""

    model_config = ConfigDict(extra="ignore")

    audio: bytes | None = None
    mime_type: str = "audio/mpeg"
    format: str = "mp3"
    language: str | None = None
    model: str | None = None
    cost_usd: float = 0.0
    latency_s: float | None = None
    blocked: bool = False
    reason: str | None = None
    error: str | None = None
    available: bool = False

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class VoicePreference(BaseModel):
    model_config = ConfigDict(extra="ignore")

    voice_preference: bool = False
    preferred_language: str | None = None
    updated_at: str | None = None


def normalize_voice_language(code: str | None) -> str:
    if not code:
        return "en"
    key = str(code).strip().lower()
    return LANGUAGE_ALIASES.get(key, "en" if key not in {"si", "ta", "en"} else key)


def language_display_name(code: str | None) -> str:
    return LANGUAGE_NAMES.get(normalize_voice_language(code), "English")


def detect_voice_preference_request(text: str | None) -> bool:
    blob = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not blob:
        return False
    return any(phrase in blob for phrase in VOICE_PREF_PHRASES)


def _read_prefs() -> dict[str, Any]:
    if not _PREF_PATH.exists():
        return {}
    try:
        payload = json.loads(_PREF_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_prefs(payload: dict[str, Any]) -> None:
    _PREF_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PREF_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(_PREF_PATH)


def get_voice_preference(worker_id: str | None) -> VoicePreference:
    key = (worker_id or "").strip()
    if not key:
        return VoicePreference()
    with _PREF_LOCK:
        row = _read_prefs().get(key) or {}
    if not isinstance(row, dict):
        return VoicePreference()
    return VoicePreference.model_validate(row)


def set_voice_preference(
    worker_id: str | None,
    *,
    voice_preference: bool = True,
    preferred_language: str | None = None,
) -> VoicePreference:
    key = (worker_id or "").strip()
    if not key:
        return VoicePreference(voice_preference=voice_preference, preferred_language=preferred_language)
    pref = VoicePreference(
        voice_preference=bool(voice_preference),
        preferred_language=normalize_voice_language(preferred_language) if preferred_language else None,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    with _PREF_LOCK:
        payload = _read_prefs()
        existing = payload.get(key) if isinstance(payload.get(key), dict) else {}
        merged = dict(existing)
        merged.update(pref.model_dump(exclude_none=True))
        payload[key] = merged
        _write_prefs(payload)
    return pref


def resolve_voice_language(
    *,
    preferred_language: str | None = None,
    detected_language: str | None = None,
    session_language: str | None = None,
) -> str:
    for candidate in (preferred_language, detected_language, session_language):
        if candidate:
            return normalize_voice_language(candidate)
    return "en"


def should_send_voice_reply(
    *,
    worker_id: str | None,
    voice_used: bool = False,
    text: str | None = None,
) -> bool:
    if voice_used:
        set_voice_preference(worker_id, voice_preference=True)
        return True
    if detect_voice_preference_request(text):
        set_voice_preference(worker_id, voice_preference=True)
        return True
    return bool(get_voice_preference(worker_id).voice_preference)


async def synthesize_speech(text: str, language: str = "en", *, router: Any | None = None) -> SpeechResult:
    """Synthesize spoken guidance. Returns empty/blocked result on failure — never raises for budget."""
    body = (text or "").strip()
    if not body:
        return SpeechResult(error="empty_text", reason="empty_text")
    lang = normalize_voice_language(language)
    try:
        if router is None:
            from tools.model_router import get_model_router

            router = get_model_router()
        result = await router.synthesize_speech(text=body, language=lang)
        if isinstance(result, SpeechResult):
            return result
        if isinstance(result, dict):
            audio = result.get("audio")
            return SpeechResult(
                audio=audio if isinstance(audio, (bytes, bytearray)) else None,
                mime_type=str(result.get("mime_type") or "audio/mpeg"),
                format=str(result.get("format") or "mp3"),
                language=lang,
                model=result.get("model"),
                cost_usd=float(result.get("cost_usd") or 0),
                latency_s=result.get("latency_s"),
                blocked=bool(result.get("blocked")),
                reason=result.get("reason"),
                error=result.get("error"),
                available=bool(result.get("available") or result.get("audio")),
            )
        return SpeechResult(error="tts_failed", reason="invalid_router_result", language=lang)
    except Exception as exc:
        log.warning("tts_failed language=%s reason=%s", lang, type(exc).__name__)
        return SpeechResult(error="tts_failed", reason=type(exc).__name__, language=lang)


def reset_voice_preferences_for_tests() -> None:
    with _PREF_LOCK:
        if _PREF_PATH.exists():
            try:
                _PREF_PATH.unlink()
            except OSError:
                pass
