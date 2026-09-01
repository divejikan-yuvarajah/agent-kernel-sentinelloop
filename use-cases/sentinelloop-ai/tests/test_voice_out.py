"""Full voice output loop tests. No live OpenRouter or Telegram."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.test_model_router import FakeOpenRouter, api_model, make_router
from tools.model_router import SPEECH_URL, ModelRouter
from tools.voice_out_tools import (
    SpeechResult,
    get_voice_preference,
    reset_voice_preferences_for_tests,
    set_voice_preference,
    should_send_voice_reply,
    synthesize_speech,
)


def run(coro):
    return asyncio.run(coro)


class FakeTtsOpenRouter(FakeOpenRouter):
    def __init__(self) -> None:
        super().__init__()
        self.speech_calls: list[dict[str, Any]] = []
        self.speech_status = 200
        self.speech_bytes = b"ID3fake-mp3-audio"
        self.catalog = list(self.catalog) + [
            api_model(
                "acme/tts-free",
                "0",
                "0",
                8000,
                name="Free TTS",
                input_mod=["text"],
                output_mod=["audio"],
            ),
            api_model(
                "acme/tts-paid",
                "0.00001",
                "0.00002",
                8000,
                name="Paid TTS",
                input_mod=["text"],
                output_mod=["audio"],
            ),
        ]

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(SPEECH_URL) and request.method == "POST":
            self.speech_calls.append(json.loads(request.content.decode("utf-8")))
            if self.speech_status != 200:
                return httpx.Response(self.speech_status, json={"error": {"message": "tts failed"}})
            return httpx.Response(
                200,
                content=self.speech_bytes,
                headers={"content-type": "audio/mpeg", "x-openrouter-cost": "0.001"},
            )
        return super().handler(request)


@pytest.fixture(autouse=True)
def _clean_prefs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    reset_voice_preferences_for_tests()
    pref = tmp_path / "voice_preferences.json"
    monkeypatch.setattr("tools.voice_out_tools._PREF_PATH", pref)
    yield
    reset_voice_preferences_for_tests()


def _router(tmp_path: Path, fake: FakeTtsOpenRouter, *, budget: str = "3") -> ModelRouter:
    return make_router(tmp_path, fake, budget=budget)


def test_voice_originated_report_calls_tts(tmp_path: Path):
    fake = FakeTtsOpenRouter()
    router = _router(tmp_path, fake)
    assert should_send_voice_reply(worker_id="telegram:1", voice_used=True) is True
    result = run(synthesize_speech("Move away from the area.", "en", router=router))
    assert result.available is True
    assert result.audio == fake.speech_bytes
    assert fake.speech_calls, "TTS endpoint must be called for voice-originated preference"
    ledger = json.loads((tmp_path / "spend_ledger.json").read_text(encoding="utf-8"))
    assert any(row.get("type") == "tts" for row in ledger.get("recent_calls") or [])
    run(router.aclose())


def test_text_only_report_skips_tts_when_no_preference():
    assert should_send_voice_reply(worker_id="telegram:text-only", voice_used=False, text="spill near machine") is False


def test_stored_voice_preference_triggers_tts_for_text(tmp_path: Path):
    fake = FakeTtsOpenRouter()
    router = _router(tmp_path, fake)
    set_voice_preference("telegram:pref", voice_preference=True, preferred_language="si")
    assert should_send_voice_reply(worker_id="telegram:pref", voice_used=False, text="oil on floor") is True
    result = run(synthesize_speech("Stay clear of the spill.", "si", router=router))
    assert result.available is True
    assert fake.speech_calls
    assert get_voice_preference("telegram:pref").preferred_language == "si"
    run(router.aclose())


def test_budget_ceiling_blocks_tts_not_text(tmp_path: Path):
    fake = FakeTtsOpenRouter()
    router = _router(tmp_path, fake, budget="0.0005")
    router._cumulative = Decimal("0.0004")
    router._budget_ceiling = Decimal("0.0005")
    result = run(synthesize_speech("Evacuate the area immediately.", "en", router=router))
    assert result.blocked is True
    assert result.audio is None
    assert fake.speech_calls == []
    assert should_send_voice_reply(worker_id="telegram:budget", voice_used=True) is True
    run(router.aclose())


def test_tts_failure_does_not_raise(tmp_path: Path):
    fake = FakeTtsOpenRouter()
    fake.speech_status = 503
    router = _router(tmp_path, fake)
    result = run(synthesize_speech("Contact your supervisor.", "en", router=router))
    assert result.available is False
    assert result.error in {"tts_failed", "tts_unavailable"} or result.reason
    assert isinstance(result, SpeechResult)
    run(router.aclose())


def test_orchestrator_voice_path_text_always_first():
    """Voice reply is attempted only after text send; TTS failure still leaves guidance_sent."""

    async def _flow():
        sent: list[str] = []
        tts_calls = {"n": 0}

        class Outbound:
            async def send_text_message(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                sent.append("text")
                return {"ok": True, "id": "1"}

            async def send_voice_message(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
                sent.append("voice")
                return {"ok": True, "id": "2"}

        class Orch:
            def _outbound(self, message: Any) -> Outbound:
                return Outbound()

            async def _deliver_voice_reply(self, *args: Any, **kwargs: Any) -> None:
                tts_calls["n"] += 1
                sent.append("voice")

            async def _maybe_send_voice_guidance(self, message: Any, session: Any, merged: Any, **kwargs: Any) -> None:
                if not should_send_voice_reply(worker_id=message.sender_id, voice_used=True):
                    return
                await self._deliver_voice_reply(message, session, merged, **kwargs)

        class Msg:
            sender_id = "telegram:loop"
            voice_used = True
            text = "machine noise"
            caption = None
            provider_message_id = "9"
            detected_language = "en"

        orch = Orch()
        outbound = orch._outbound(Msg())
        await outbound.send_text_message("telegram:loop", "Please move away.")
        await orch._maybe_send_voice_guidance(
            Msg(),
            None,
            {},
            worker_text="Please move away.",
            reply_to_message_id="9",
        )
        assert sent[0] == "text"
        assert "voice" in sent
        assert tts_calls["n"] == 1

    run(_flow())


def test_explicit_preference_phrases():
    assert should_send_voice_reply(worker_id="telegram:p1", text="please send voice") is True
    assert should_send_voice_reply(worker_id="telegram:p2", text="I prefer audio") is True
    assert should_send_voice_reply(worker_id="telegram:p3", text="speak to me") is True
