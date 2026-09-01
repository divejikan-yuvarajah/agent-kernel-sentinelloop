"""Telegram transport tests. No live Telegram API or Agent Kernel runtime."""

from __future__ import annotations

import asyncio
import base64

from integrations.inbound import NormalizedInboundMessage
from integrations.telegram_handler import (
    SentinelLoopTelegramHandler,
    TelegramTransport,
    discover_recent_chat_id,
    is_start_command,
    largest_photo,
    normalize_telegram_update,
    reset_telegram_health,
    resolve_start_tag,
    rewrite_qr_kv,
    session_key,
    start_command_handler,
    start_payload,
)
from tools.duplicate_tools import DuplicateResult
from tools.emergency_bypass import is_emergency_trigger
from tools.voice_tools import transcribe_voice_note


def run(coro):
    return asyncio.run(coro)


def _update(message: dict) -> dict:
    return {"message": message}


def _text(text: str, *, chat_id: int = 48291033, message_id: int = 1) -> dict:
    return _update(
        {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "from": {"id": 9001, "username": "kamal", "language_code": "si"},
            "text": text,
        }
    )


class RecordingOrchestrator:
    def __init__(self) -> None:
        self.messages: list[NormalizedInboundMessage] = []
        self.order: list[str] = []

    async def process_incoming_telegram_message(self, message: NormalizedInboundMessage):
        self.order.append("orchestrator")
        self.messages.append(message)
        return message


class FakeTelegramClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.files: dict[str, bytes] = {}

    async def __call__(self, method: str, payload):
        self.calls.append((method, payload))
        if method == "getFile":
            return {"content": self.files.get(str(payload), b"ogg-bytes"), "mime_type": "audio/ogg"}
        return {"ok": True, "result": {"message_id": 77}}


def test_session_key_uses_chat_id_not_username():
    assert session_key(48291033) == "telegram:48291033"
    normalized = normalize_telegram_update(_text("oil leak"))
    assert normalized is not None
    assert normalized.sender_id == "telegram:48291033"
    assert normalized.username == "kamal"
    assert normalized.input_channel == "telegram"


def test_normalize_text_passes_raw_text():
    normalized = normalize_telegram_update(_text("Machine area smoke coming"))
    assert normalized is not None
    assert normalized.text == "Machine area smoke coming"
    assert normalized.message_type == "text"


def test_qr_kv_rewritten_to_slqr():
    text = rewrite_qr_kv("QR_LOCATION=CNC Area\nQR_EQUIPMENT=CNC-04\n\nMachine is vibrating badly")
    assert 'location="CNC Area"' in text
    assert 'equipment="CNC-04"' in text
    assert "Machine is vibrating badly" in text
    assert text.startswith("SLQR")


def test_largest_photo_selected():
    photos = [
        {"file_id": "small", "file_size": 100, "width": 90},
        {"file_id": "large", "file_size": 9000, "width": 1280},
        {"file_id": "mid", "file_size": 400, "width": 320},
    ]
    chosen = largest_photo(photos)
    assert chosen is not None
    assert chosen["file_id"] == "large"
    update = _update(
        {
            "message_id": 9,
            "chat": {"id": 1},
            "from": {"id": 1},
            "photo": photos,
            "caption": "sparking panel",
        }
    )
    normalized = normalize_telegram_update(update)
    assert normalized is not None
    assert normalized.message_type == "image"
    assert normalized.media is not None
    assert normalized.media.media_id == "large"


def test_stickers_ignored():
    update = _update(
        {
            "message_id": 3,
            "chat": {"id": 1},
            "from": {"id": 1},
            "sticker": {"file_id": "sticker-1"},
        }
    )
    normalized = normalize_telegram_update(update)
    assert normalized is not None
    assert normalized.supported is False
    assert normalized.message_type == "sticker"


def test_location_attached():
    update = _update(
        {
            "message_id": 4,
            "chat": {"id": 11},
            "from": {"id": 11},
            "location": {"latitude": 7.123, "longitude": 79.88},
        }
    )
    normalized = normalize_telegram_update(update)
    assert normalized is not None
    assert normalized.latitude == 7.123
    assert normalized.longitude == 79.88


def test_emergency_trigger_examples():
    assert is_emergency_trigger("Fire now")
    assert is_emergency_trigger("chemical leaking")
    assert is_emergency_trigger("machine explosion")
    assert is_emergency_trigger("electric shock")
    assert not is_emergency_trigger("good morning")


def test_start_command_sends_status_card_not_incident():
    reset_telegram_health()
    orch = RecordingOrchestrator()
    client = FakeTelegramClient()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=client),
        skip_kernel_init=True,
    )
    result = run(handler.handle_incoming_update(_text("/start")))
    assert result is None
    assert orch.messages == []
    assert client.calls and client.calls[0][0] == "sendMessage"
    payload = client.calls[0][1]
    assert "Safety Report Received" in payload["text"]
    assert payload["chat_id"] == "48291033"


def test_my_chat_member_sends_status_card():
    reset_telegram_health()
    orch = RecordingOrchestrator()
    client = FakeTelegramClient()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=client),
        skip_kernel_init=True,
    )
    result = run(
        handler.handle_incoming_update(
            {
                "update_id": 9,
                "my_chat_member": {
                    "chat": {"id": 77, "type": "private"},
                    "new_chat_member": {"status": "member"},
                },
            }
        )
    )
    assert result is None
    assert orch.messages == []
    assert client.calls and client.calls[0][0] == "sendMessage"
    assert client.calls[0][1]["chat_id"] == "77"


def test_is_start_command():
    assert is_start_command("/start")
    assert is_start_command("/start@SentinelLoop_ReportBot")
    assert not is_start_command("start the machine")
    assert start_payload("/start SNT-LAB-B-M4-001") == "SNT-LAB-B-M4-001"
    assert start_payload("/start") is None
    handler = start_command_handler(lambda update, context: None)
    assert "start" in handler.commands
    assert resolve_start_tag("SNT-LAB-B-M4-001") == "[LOC:Lab B|Machine 4]"


def test_start_tag_enters_pipeline_with_location():
    reset_telegram_health()
    orch = RecordingOrchestrator()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=FakeTelegramClient()),
        skip_kernel_init=True,
    )
    run(handler.handle_incoming_update(_text("/start SNT-LAB-B-M4-001")))
    assert orch.messages
    assert orch.messages[0].text == "[LOC:Lab B|Machine 4]"
    assert orch.messages[0].sender_id == "telegram:48291033"


def test_text_message_enters_pipeline():
    reset_telegram_health()
    orch = RecordingOrchestrator()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=FakeTelegramClient()),
        skip_kernel_init=True,
    )
    result = run(handler.handle_incoming_update(_text("The electrical panel is sparking.")))
    assert result is not None
    assert orch.messages[0].text == "The electrical panel is sparking."
    assert orch.messages[0].input_channel == "telegram"


def test_image_message_downloads_largest_and_sets_has_image():
    reset_telegram_health()
    client = FakeTelegramClient()
    client.files["large"] = b"\xff\xd8jpeg"
    orch = RecordingOrchestrator()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=client),
        skip_kernel_init=True,
    )
    update = _update(
        {
            "message_id": 12,
            "chat": {"id": 44},
            "from": {"id": 44},
            "photo": [
                {"file_id": "small", "file_size": 10},
                {"file_id": "large", "file_size": 5000},
            ],
            "caption": "oil on the floor",
        }
    )
    run(handler.handle_incoming_update(update))
    message = orch.messages[0]
    assert message.media is not None
    assert message.media.content == b"\xff\xd8jpeg"
    assert message.media.media_id == "large"
    get_file = [call for call in client.calls if call[0] == "getFile"]
    assert get_file and get_file[0][1] == "large"


def test_voice_message_base64_ogg_transcribed():
    reset_telegram_health()
    client = FakeTelegramClient()
    client.files["voice-1"] = b"opus-ogg"
    seen: dict[str, object] = {}

    def transcribe(audio_b64: str, *, audio_format: str = "ogg", **kwargs):
        seen["b64"] = audio_b64
        seen["format"] = audio_format
        return "Machine area smoke coming"

    orch = RecordingOrchestrator()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    update = _update(
        {
            "message_id": 13,
            "chat": {"id": 55},
            "from": {"id": 55},
            "voice": {"file_id": "voice-1", "duration": 18, "mime_type": "audio/ogg"},
        }
    )
    run(handler.handle_incoming_update(update))
    assert seen["format"] == "ogg"
    assert seen["b64"] == base64.b64encode(b"opus-ogg").decode("ascii")
    message = orch.messages[0]
    assert message.text == "Machine area smoke coming"
    assert message.voice_used is True
    assert message.audio_format == "ogg"
    assert message.transcription_available is True


def test_voice_transcription_failure_asks_for_text():
    reset_telegram_health()
    client = FakeTelegramClient()
    client.files["voice-2"] = b"bad"

    def transcribe(*args, **kwargs):
        raise RuntimeError("unavailable")

    orch = RecordingOrchestrator()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=client),
        skip_kernel_init=True,
        transcribe_fn=transcribe,
    )
    update = _update(
        {
            "message_id": 14,
            "chat": {"id": 56},
            "from": {"id": 56},
            "voice": {"file_id": "voice-2", "duration": 4},
        }
    )
    run(handler.handle_incoming_update(update))
    assert orch.messages == []
    sends = [call for call in client.calls if call[0] == "sendMessage"]
    assert sends


def test_same_chat_id_continues_session():
    reset_telegram_health()
    orch = RecordingOrchestrator()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=FakeTelegramClient()),
        skip_kernel_init=True,
    )
    run(handler.handle_incoming_update(_text("Where is the hazard located?", chat_id=77, message_id=1)))
    run(handler.handle_incoming_update(_text("Near machine 4", chat_id=77, message_id=2)))
    assert [item.sender_id for item in orch.messages] == ["telegram:77", "telegram:77"]


def test_emergency_bypass_runs_first():
    reset_telegram_health()
    order: list[str] = []

    def emergency(text: str | None) -> bool:
        order.append("emergency")
        return is_emergency_trigger(text)

    class OrderedOrch(RecordingOrchestrator):
        async def process_incoming_telegram_message(self, message: NormalizedInboundMessage):
            order.append("orchestrator")
            return await super().process_incoming_telegram_message(message)

    orch = OrderedOrch()
    handler = SentinelLoopTelegramHandler(
        orchestrator=orch,
        transport=TelegramTransport(client=FakeTelegramClient()),
        skip_kernel_init=True,
        emergency_fn=emergency,
    )
    run(handler.handle_incoming_update(_text("Fire now")))
    assert order == ["emergency", "orchestrator"]
    assert orch.messages[0].emergency_bypass is True


def test_duplicate_telegram_reuses_canonical_incident():
    from agentkernel.core.session.in_memory import InMemorySessionStore

    from integrations.incident_orchestrator import IncidentOrchestrator
    from integrations.telegram_handler import TelegramTransport
    from tests.test_incident_orchestrator import (
        FakeCoord,
        MemoryRepo,
        RecordingClient,
        Scripted,
        _guidance,
        _incident,
        _intake,
        _risk,
    )

    repo = MemoryRepo()

    def duplicate_fn(query, repository=None):
        if repository is not None and getattr(repository, "create_calls", None):
            created = repository.create_calls[0]
            uid = repository.by_ref.get(created.incident_ref)
            return DuplicateResult(
                status="confirmed",
                action="reuse",
                canonical_incident_id=created.incident_ref,
                canonical_uuid=uid,
                preserve_status=True,
            )
        return DuplicateResult(status="none", action="create_new")

    orch = IncidentOrchestrator(
        repository=repo,
        telegram=TelegramTransport(client=FakeTelegramClient()),
        coordination=FakeCoord(),
        intake_fn=Scripted("intake", default=_intake()),
        duplicate_fn=duplicate_fn,
        incident_fn=Scripted("incident", default=_incident()),
        risk_fn=Scripted("risk", default=_risk()),
        guidance_fn=Scripted("guidance", default=_guidance()),
        session_store=InMemorySessionStore(),
    )
    first = run(
        orch.process_incoming_telegram_message(
            NormalizedInboundMessage(
                provider_message_id="tg.spark-1",
                sender_id="telegram:1001",
                message_type="text",
                text="Machine sparking",
                input_channel="telegram",
                chat_id="1001",
            )
        )
    )
    second = run(
        orch.process_incoming_telegram_message(
            NormalizedInboundMessage(
                provider_message_id="tg.spark",
                sender_id="telegram:48291033",
                message_type="text",
                text="Same machine sparks",
                input_channel="telegram",
                chat_id="48291033",
            )
        )
    )
    assert first.canonical_incident_id
    assert second.duplicate_detected is True
    assert second.canonical_incident_id == first.canonical_incident_id
    assert repo.create_calls[0].source_channel == "telegram"
    assert all(row.source_channel != "telegram" for row in repo.create_calls[1:])


def test_telegram_create_stores_input_channel():
    from agentkernel.core.session.in_memory import InMemorySessionStore

    from integrations.incident_orchestrator import IncidentOrchestrator
    from integrations.telegram_handler import TelegramTransport
    from tests.test_incident_orchestrator import (
        FakeCoord,
        MemoryRepo,
        RecordingClient,
        Scripted,
        _guidance,
        _incident,
        _intake,
        _risk,
    )

    repo = MemoryRepo()
    orch = IncidentOrchestrator(
        repository=repo,
        telegram=TelegramTransport(client=FakeTelegramClient()),
        coordination=FakeCoord(),
        intake_fn=Scripted("intake", default=_intake(raw_text="Machine area smoke coming")),
        duplicate_fn=lambda query, repository=None: DuplicateResult(status="none", action="create_new"),
        incident_fn=Scripted("incident", default=_incident(location="CNC Area")),
        risk_fn=Scripted("risk", default=_risk(level="High", score=16)),
        guidance_fn=Scripted("guidance", default=_guidance()),
        session_store=InMemorySessionStore(),
    )
    result = run(
        orch.process_incoming_telegram_message(
            NormalizedInboundMessage(
                provider_message_id="tg.smoke",
                sender_id="telegram:48291033",
                message_type="text",
                text="Machine area smoke coming",
                input_channel="telegram",
                chat_id="48291033",
            )
        )
    )
    assert result.is_hazard_report is True
    assert repo.create_calls[0].source_channel == "telegram"
    assert repo.create_calls[0].reporter_id == "telegram:48291033"


def test_voice_tools_never_fabricates():
    empty = run(transcribe_voice_note("", audio_format="ogg"))
    assert empty.available is False
    assert empty.text == ""


def test_discover_recent_chat_id_uses_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "48291033")
    assert run(discover_recent_chat_id()) == "48291033"
