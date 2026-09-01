"""Voice transcription tests. No live OpenRouter, Telegram, or Telegram calls."""

from __future__ import annotations

import asyncio
import base64
import json
from decimal import Decimal
from pathlib import Path

import httpx

from integrations.telegram_handler import SentinelLoopTelegramHandler, TelegramTransport, normalize_telegram_update
from tests.test_model_router import FakeOpenRouter, make_router
from tools.model_router import TRANSCRIPTIONS_URL, ModelRouter
from tools.voice_tools import (
    BUDGET_BLOCK_REASON,
    VOICE_INVALID_MESSAGE,
    VOICE_RETRY_MESSAGE,
    transcribe_voice_note,
    worker_voice_fallback_message,
)

AUDIO_BYTES = b"OggS" + b"\x00" * 64
AUDIO_B64 = base64.b64encode(AUDIO_BYTES).decode("ascii")


def run(coro):
    return asyncio.run(coro)


class FakeAudioOpenRouter(FakeOpenRouter):
    def __init__(self) -> None:
        super().__init__()
        self.transcription_calls: list[dict] = []
        self.transcription_status = 200
        self.transcription_body: dict = {
            "text": "Machine area has smoke",
            "language": "si",
            "confidence": 0.92,
            "model": "openai/whisper-large-v3",
            "usage": {"cost": 0.0012},
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(TRANSCRIPTIONS_URL) and request.method == "POST":
            self.transcription_calls.append(json.loads(request.content.decode("utf-8")))
            if self.transcription_status != 200:
                return httpx.Response(self.transcription_status, json={"error": {"message": "unavailable"}})
            return httpx.Response(200, json=self.transcription_body)
        return super().handler(request)


def _router(tmp_path: Path, fake: FakeAudioOpenRouter, *, budget: str = "3") -> ModelRouter:
    return make_router(tmp_path, fake, budget=budget)


def test_successful_transcription_language_and_cost(tmp_path: Path):
    fake = FakeAudioOpenRouter()
    router = _router(tmp_path, fake)
    result = run(transcribe_voice_note(AUDIO_B64, "ogg", "si", router=router))
    assert result["text"] == "Machine area has smoke"
    assert result["detected_language"] == "si"
    assert result["cost_usd"] == 0.0012
    assert result.available is True
    assert result.blocked is False
    assert fake.transcription_calls[0]["audio"] == AUDIO_B64
    assert fake.transcription_calls[0]["format"] == "ogg"
    assert fake.transcription_calls[0]["language"] == "si"
    ledger = json.loads((tmp_path / "spend_ledger.json").read_text(encoding="utf-8"))
    assert any(row.get("type") == "audio_transcription" for row in ledger.get("recent_calls") or [])
    run(router.aclose())


def test_invalid_transcription_response(tmp_path: Path):
    fake = FakeAudioOpenRouter()
    fake.transcription_body = {"unexpected": True}
    router = _router(tmp_path, fake)
    result = run(transcribe_voice_note(AUDIO_B64, "ogg", "en", router=router))
    assert result.available is False
    assert result.text == ""
    assert result.error == "empty_transcript"
    run(router.aclose())


def test_unsupported_format_never_calls_model(tmp_path: Path):
    fake = FakeAudioOpenRouter()
    router = _router(tmp_path, fake)
    result = run(transcribe_voice_note(AUDIO_B64, "exe", None, router=router))
    assert result.error == "unsupported_format"
    assert fake.transcription_calls == []
    run(router.aclose())


def test_invalid_audio_never_fabricates():
    result = run(transcribe_voice_note("@@@not-base64!!!", "ogg", "en"))
    assert result.text == ""
    assert result.error in {"invalid_audio", "empty_audio"}
    assert result.available is False


def test_empty_audio_never_fabricates():
    result = run(transcribe_voice_note("", "ogg", None))
    assert result.available is False
    assert result.text == ""


def test_budget_governor_blocks_before_model_call(tmp_path: Path):
    fake = FakeAudioOpenRouter()
    router = _router(tmp_path, fake, budget="0.01")
    router._cumulative = Decimal("0.0095")
    result = run(transcribe_voice_note(AUDIO_B64, "ogg", "si", router=router))
    assert result["blocked"] is True
    assert result["reason"] == BUDGET_BLOCK_REASON
    assert fake.transcription_calls == []
    run(router.aclose())


def test_audio_api_unavailable_returns_controlled_error(tmp_path: Path):
    fake = FakeAudioOpenRouter()
    fake.transcription_status = 503
    router = _router(tmp_path, fake)
    result = run(transcribe_voice_note(AUDIO_B64, "ogg", "en", router=router))
    assert result.text == ""
    assert result.error == "transcription_failed"
    assert result.available is False
    run(router.aclose())


def test_worker_messages_for_failures():
    from tools.voice_tools import TranscriptionResult

    assert VOICE_RETRY_MESSAGE in worker_voice_fallback_message(
        TranscriptionResult(error="empty_transcript", transcription_confidence=0.2)
    )
    assert VOICE_INVALID_MESSAGE in worker_voice_fallback_message(TranscriptionResult(error="invalid_audio"))
    blocked = TranscriptionResult(blocked=True, reason=BUDGET_BLOCK_REASON, error="budget_exceeded")
    assert "text description" in worker_voice_fallback_message(blocked).lower()


class RecordingOrch:
    def __init__(self) -> None:
        self.messages = []

    async def process_incoming_telegram_message(self, message):
        self.messages.append(message)
        return message


def _voice_update(*, file_id: str = "AUDIO1", chat_id: int = 48291033, message_id: int = 11) -> dict:
    return {
        "message": {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "from": {"id": 9001, "language_code": "en"},
            "voice": {"file_id": file_id, "duration": 8, "mime_type": "audio/ogg"},
        }
    }


class VoiceClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def __call__(self, method: str, payload):
        self.calls.append((method, payload))
        if method == "getFile":
            return {"content": AUDIO_BYTES, "mime_type": "audio/ogg"}
        return {"ok": True, "result": {"message_id": 77}}


def test_telegram_voice_payload_detected():
    normalized = normalize_telegram_update(_voice_update())
    assert normalized is not None
    assert normalized.supported is True
    assert normalized.message_type == "voice"
    assert normalized.media is not None
    assert normalized.media.media_id == "AUDIO1"
    assert normalized.sender_id == "telegram:48291033"


def test_telegram_voice_downloads_transcribes_and_sets_input_method():
    seen: dict[str, object] = {}

    def transcribe(audio_b64: str, *, audio_format: str = "ogg", **kwargs):
        seen["b64"] = audio_b64
        seen["format"] = audio_format
        return {
            "text": "Wire is damaged near machine four",
            "detected_language": "en",
            "cost_usd": 0.001,
            "confidence": 0.92,
        }

    orch = RecordingOrch()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=VoiceClient()),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(handler.handle_incoming_update(_voice_update()))
    assert seen["format"] == "ogg"
    assert seen["b64"] == AUDIO_B64
    assert len(orch.messages) == 1
    message = orch.messages[0]
    assert message.text == "Wire is damaged near machine four"
    assert message.input_method == "voice"
    assert message.voice_used is True
    assert message.audio_used is True
    assert message.transcription_available is True
    assert message.audio_format == "ogg"


def test_telegram_text_does_not_transcribe():
    called = {"n": 0}

    def transcribe(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("transcription must not run for text")

    orch = RecordingOrch()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=VoiceClient()),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(
        handler.handle_incoming_update(
            {
                "message": {
                    "message_id": 2,
                    "chat": {"id": 48291033},
                    "from": {"id": 9001},
                    "text": "oil on the floor",
                }
            }
        )
    )
    assert called["n"] == 0
    assert orch.messages[0].text == "oil on the floor"
    assert orch.messages[0].input_method is None


def test_telegram_invalid_audio_sends_friendly_message():
    client = VoiceClient()

    def transcribe(*args, **kwargs):
        return {"error": "invalid_audio", "text": ""}

    orch = RecordingOrch()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(handler.handle_incoming_update(_voice_update(file_id="AUDIO-BAD")))
    assert orch.messages == []
    texts = [
        payload["text"] for method, payload in client.calls if method == "sendMessage" and isinstance(payload, dict)
    ]
    assert texts
    assert "voice" in texts[0].lower() or "text" in texts[0].lower()


def test_telegram_budget_exceeded_safe_fallback():
    client = VoiceClient()

    def transcribe(*args, **kwargs):
        return {"blocked": True, "reason": BUDGET_BLOCK_REASON}

    orch = RecordingOrch()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(handler.handle_incoming_update(_voice_update(file_id="AUDIO-BUDGET")))
    assert orch.messages == []
    assert any(method == "sendMessage" for method, _payload in client.calls)


def test_telegram_api_unavailable_incident_still_recoverable():
    def transcribe(*args, **kwargs):
        raise RuntimeError("openrouter down")

    orch = RecordingOrch()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=VoiceClient()),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    result = run(handler.handle_incoming_update(_voice_update(file_id="AUDIO-DOWN")))
    assert result is None
    assert orch.messages == []


def test_intake_agent_receives_raw_text_only(mock_model_router):
    from agents.intake_agent import process_intake
    from tools.model_router import ModelCallResult

    mock_model_router.response = ModelCallResult(
        content=json.dumps(
            {
                "language": "en",
                "translated_text": "Wire is damaged near machine four",
                "is_hazard_report": True,
                "language_confidence": "high",
                "hazard_confidence": "high",
                "needs_clarification": False,
            }
        ),
        model="mock/free",
        role="role_fast",
        paid=False,
    )
    result = run(
        process_intake(
            "telegram:48291033",
            "Wire is damaged near machine four",
            call_model_fn=mock_model_router,
        )
    )
    assert result.is_hazard_report is True
    assert result.raw_text == "Wire is damaged near machine four"
    assert result.message_type == "text"


def test_low_confidence_does_not_continue():
    def transcribe(*args, **kwargs):
        return {"text": "mmm unclear", "confidence": 0.2, "detected_language": "en", "cost_usd": 0.001}

    orch = RecordingOrch()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=VoiceClient()),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(handler.handle_incoming_update(_voice_update(file_id="AUDIO-LOW")))
    assert orch.messages == []
