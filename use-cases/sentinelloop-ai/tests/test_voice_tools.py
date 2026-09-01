"""Voice transcription tests. No live OpenRouter, WhatsApp, or Telegram calls."""

from __future__ import annotations

import asyncio
import base64
import json
from decimal import Decimal
from pathlib import Path

import httpx

from integrations.whatsapp_handler import (
    SentinelLoopWhatsAppHandler,
    WhatsAppCloudTransport,
    normalize_incoming_message,
)
from tools.model_router import TRANSCRIPTIONS_URL, ModelRouter
from tools.voice_tools import (
    BUDGET_BLOCK_REASON,
    VOICE_INVALID_MESSAGE,
    VOICE_RETRY_MESSAGE,
    transcribe_voice_note,
    worker_voice_fallback_message,
)
from tests.test_model_router import FakeOpenRouter, make_router

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

    async def process_incoming_whatsapp_message(self, message):
        self.messages.append(message)
        return message


def test_whatsapp_voice_payload_detected():
    payload = {
        "id": "wamid.voice",
        "from": "94771234567",
        "type": "audio",
        "timestamp": "1710000000",
        "audio": {
            "id": "AUDIO1",
            "mime_type": "audio/ogg; codecs=opus",
            "voice": True,
            "duration": 18,
        },
    }
    normalized = normalize_incoming_message(payload)
    assert normalized is not None
    assert normalized.supported is True
    assert normalized.message_type == "voice"
    assert normalized.media is not None
    assert normalized.media.media_id == "AUDIO1"
    assert normalized.audio_format == "ogg"


def test_whatsapp_voice_downloads_transcribes_and_sets_input_method():
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

    async def media_client(op, media_id):
        assert op == "download"
        assert media_id == "AUDIO1"
        return {"content": AUDIO_BYTES, "mime_type": "audio/ogg"}

    orch = RecordingOrch()
    handler = SentinelLoopWhatsAppHandler(
        orchestrator=orch,
        transport=WhatsAppCloudTransport(media_client=media_client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(
        handler.handle_incoming_webhook(
            {
                "id": "wamid.voice-1",
                "from": "94771234567",
                "type": "audio",
                "audio": {"id": "AUDIO1", "mime_type": "audio/ogg; codecs=opus", "voice": True},
            },
            {},
        )
    )
    assert seen["format"] == "ogg"
    assert seen["b64"] == AUDIO_B64
    assert len(orch.messages) == 1
    message = orch.messages[0]
    assert message.text == "Wire is damaged near machine four"
    assert message.input_method == "voice"
    assert message.voice_used is True
    assert message.audio_used is True
    assert message.transcription_available is True


def test_whatsapp_text_does_not_transcribe():
    called = {"n": 0}

    def transcribe(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("transcription must not run for text")

    orch = RecordingOrch()
    handler = SentinelLoopWhatsAppHandler(
        orchestrator=orch,
        transport=WhatsAppCloudTransport(),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(
        handler.handle_incoming_webhook(
            {
                "id": "wamid.text-1",
                "from": "94771234567",
                "type": "text",
                "text": {"body": "oil on the floor"},
            },
            {},
        )
    )
    assert called["n"] == 0
    assert orch.messages[0].text == "oil on the floor"
    assert orch.messages[0].input_method is None


def test_whatsapp_invalid_audio_sends_friendly_message():
    client_payloads: list[dict] = []

    class Client:
        async def __call__(self, payload):
            client_payloads.append(payload)
            return {"messages": [{"id": "wamid.out"}]}

    async def media_client(op, media_id):
        return {"content": AUDIO_BYTES, "mime_type": "audio/ogg"}

    def transcribe(*args, **kwargs):
        return {"error": "invalid_audio", "text": ""}

    orch = RecordingOrch()
    handler = SentinelLoopWhatsAppHandler(
        orchestrator=orch,
        transport=WhatsAppCloudTransport(client=Client(), media_client=media_client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(
        handler.handle_incoming_webhook(
            {
                "id": "wamid.voice-bad",
                "from": "9477",
                "type": "audio",
                "audio": {"id": "AUDIO-BAD", "mime_type": "audio/ogg"},
            },
            {},
        )
    )
    assert orch.messages == []
    assert client_payloads
    body = client_payloads[0]["text"]["body"]
    assert "voice" in body.lower() or "text" in body.lower()


def test_whatsapp_budget_exceeded_safe_fallback():
    client_payloads: list[dict] = []

    class Client:
        async def __call__(self, payload):
            client_payloads.append(payload)
            return {"messages": [{"id": "wamid.out"}]}

    async def media_client(op, media_id):
        return {"content": AUDIO_BYTES, "mime_type": "audio/ogg"}

    def transcribe(*args, **kwargs):
        return {"blocked": True, "reason": BUDGET_BLOCK_REASON}

    orch = RecordingOrch()
    handler = SentinelLoopWhatsAppHandler(
        orchestrator=orch,
        transport=WhatsAppCloudTransport(client=Client(), media_client=media_client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(
        handler.handle_incoming_webhook(
            {
                "id": "wamid.voice-budget",
                "from": "9477",
                "type": "audio",
                "audio": {"id": "AUDIO-BUDGET", "mime_type": "audio/ogg"},
            },
            {},
        )
    )
    assert orch.messages == []
    assert client_payloads


def test_whatsapp_api_unavailable_incident_still_recoverable():
    async def media_client(op, media_id):
        return {"content": AUDIO_BYTES, "mime_type": "audio/ogg"}

    def transcribe(*args, **kwargs):
        raise RuntimeError("openrouter down")

    orch = RecordingOrch()
    handler = SentinelLoopWhatsAppHandler(
        orchestrator=orch,
        transport=WhatsAppCloudTransport(media_client=media_client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    result = run(
        handler.handle_incoming_webhook(
            {
                "id": "wamid.voice-down",
                "from": "9477",
                "type": "audio",
                "audio": {"id": "AUDIO-DOWN", "mime_type": "audio/ogg"},
            },
            {},
        )
    )
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
            "94771234567",
            "Wire is damaged near machine four",
            call_model_fn=mock_model_router,
        )
    )
    assert result.is_hazard_report is True
    assert result.raw_text == "Wire is damaged near machine four"
    assert result.message_type == "text"


def test_low_confidence_does_not_continue():
    async def media_client(op, media_id):
        return {"content": AUDIO_BYTES, "mime_type": "audio/ogg"}

    def transcribe(*args, **kwargs):
        return {"text": "mmm unclear", "confidence": 0.2, "detected_language": "en", "cost_usd": 0.001}

    orch = RecordingOrch()
    handler = SentinelLoopWhatsAppHandler(
        orchestrator=orch,
        transport=WhatsAppCloudTransport(media_client=media_client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    run(
        handler.handle_incoming_webhook(
            {
                "id": "wamid.voice-low",
                "from": "9477",
                "type": "audio",
                "audio": {"id": "AUDIO-LOW", "mime_type": "audio/ogg"},
            },
            {},
        )
    )
    assert orch.messages == []
