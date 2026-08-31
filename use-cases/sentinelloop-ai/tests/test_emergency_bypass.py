"""Emergency bypass gate and instant-response path. No live network or LLM."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from agentkernel.core.session.in_memory import InMemorySessionStore

from database.schemas import IncidentCreate
from guardrails.emergency_bypass import detect_emergency, extract_possible_location, is_emergency_trigger
from guardrails.emergency_keywords import WORKER_EMERGENCY_REPLY
from integrations.incident_orchestrator import IncidentOrchestrator
from integrations.slack_handler import SlackHandler, SlackPostError
from integrations.whatsapp import WhatsAppSendError
from integrations.whatsapp_handler import NormalizedWhatsAppMessage, SentinelLoopWhatsAppHandler, WhatsAppCloudTransport
from tools.duplicate_tools import DuplicateResult
from tools.model_router import call_model as live_call_model


def run(coro):
    return asyncio.run(coro)


class RecordingWhatsApp:
    def __init__(self) -> None:
        self.payloads: list[str] = []
        self.fail = False
        self.calls = 0

    async def send_text_message(self, to: str, text: str, **kwargs):
        self.calls += 1
        if self.fail:
            raise WhatsAppSendError("whatsapp down")
        self.payloads.append(text)
        return {"id": f"wamid.out.{self.calls}"}


class FakeSlackClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.fail: str | None = None

    async def chat_postMessage(self, **kwargs):
        if self.fail:
            raise RuntimeError("slack down")
        self.posts.append(kwargs)
        return {"ok": True, "ts": "1.0", "channel": kwargs.get("channel")}


class MemoryRepo:
    def __init__(self) -> None:
        self.create_calls: list[IncidentCreate] = []
        self.updates: list[object] = []
        self.field_updates: list[tuple] = []
        self.rows: list[dict] = []

    def create_incident(self, data: IncidentCreate):
        self.create_calls.append(data)
        uid = uuid4()
        row = {"id": uid, "incident_ref": data.incident_ref, "duplicate_count": 0, **data.model_dump()}
        self.rows.append(row)
        return SimpleNamespace(**row)

    def update_incident_fields(self, incident_id, fields):
        self.field_updates.append((incident_id, fields))
        return SimpleNamespace(id=incident_id, **fields)

    def update_incident_status(self, incident_id, status):
        return self.update_incident_fields(incident_id, {"status": status})

    def add_update(self, data):
        self.updates.append(data)
        return data

    def get_incident(self, incident_id):
        for row in self.rows:
            if row["id"] == incident_id:
                return SimpleNamespace(**row)
        return None


class Scripted:
    def __init__(self, name: str, default: dict) -> None:
        self.name = name
        self.default = default
        self.calls: list[tuple] = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(**self.default)


def _msg(**kwargs) -> NormalizedWhatsAppMessage:
    data = {
        "provider_message_id": kwargs.pop("provider_message_id", f"wamid.{uuid4()}"),
        "sender_id": kwargs.pop("sender_id", "94771234567"),
        "message_type": "text",
        "text": "SOS",
        "received_at": datetime.now(timezone.utc),
        "supported": True,
        "input_channel": "whatsapp",
    }
    data.update(kwargs)
    return NormalizedWhatsAppMessage.model_validate(data)


class FakeCoord:
    async def coordinate_incident(self, *args, **kwargs):
        return SimpleNamespace(posted=True, slack_channel_id="C-EMRG", assigned_team="Emergency Response Team")


def _orch(**kwargs) -> IncidentOrchestrator:
    repo = kwargs.pop("repository", MemoryRepo())
    whatsapp = kwargs.pop("whatsapp", RecordingWhatsApp())
    slack_client = kwargs.pop("slack_client", FakeSlackClient())
    intake = kwargs.pop(
        "intake_fn", Scripted("intake", {"raw_text": "SOS", "is_hazard_report": True, "language": "en"})
    )
    incident = kwargs.pop(
        "incident_fn",
        Scripted(
            "incident",
            {
                "hazard_category": "fire/smoke",
                "location": "welding section",
                "skip_clarification": True,
                "needs_clarification": False,
            },
        ),
    )

    class Guidance:
        text = "Stay back."
        knowledge_grounded = True

        def worker_text(self) -> str:
            return self.text

    async def guidance_fn(*args, **kwargs):
        return Guidance()

    orch = IncidentOrchestrator(
        repository=repo,
        whatsapp=whatsapp,
        slack=SlackHandler(
            client=slack_client,
            destinations={"Emergency Response Team": "C-EMRG"},
        ),
        intake_fn=intake,
        incident_fn=incident,
        risk_fn=kwargs.pop("risk_fn", Scripted("risk", {"level": "Critical", "score": 25, "explanation": "emergency"})),
        guidance_fn=kwargs.pop("guidance_fn", guidance_fn),
        duplicate_fn=kwargs.pop(
            "duplicate_fn",
            lambda query, repository=None: DuplicateResult(status="none", action="create_new"),
        ),
        coordination=kwargs.pop("coordination", FakeCoord()),
        session_store=kwargs.pop("session_store", InMemorySessionStore()),
        **kwargs,
    )
    orch._repo = repo
    orch._whatsapp_transport = whatsapp
    orch._slack_client = slack_client
    orch._intake_script = intake
    orch._incident_script = incident
    return orch


def test_english_sos_is_emergency():
    assert is_emergency_trigger("SOS") is True


def test_emoji_fire_is_emergency():
    assert is_emergency_trigger("🔥🔥") is True


def test_sinhala_approved_phrase_is_emergency():
    assert is_emergency_trigger("අනතුර") is True


def test_tamil_approved_phrase_is_emergency():
    assert is_emergency_trigger("ஆபத்து") is True


def test_normal_safety_meeting_is_not_emergency():
    assert is_emergency_trigger("Safety meeting tomorrow") is False
    assert is_emergency_trigger("Emergency training tomorrow") is False
    assert is_emergency_trigger("Fire safety meeting") is False


def test_punctuation_and_emoji_combo():
    match = detect_emergency("SOS!!! machine fire 🔥")
    assert match.triggered is True
    assert match.execution_time_ms < 100


def test_existing_life_safety_cues_still_match():
    assert is_emergency_trigger("Fire now")
    assert is_emergency_trigger("chemical leaking")
    assert is_emergency_trigger("machine explosion")
    assert is_emergency_trigger("electric shock")
    assert not is_emergency_trigger("good morning")


def test_detection_under_100ms():
    match = detect_emergency("Fire near welding section 🔥")
    assert match.triggered is True
    assert match.execution_time_ms < 100


def test_possible_location_extracted_locally():
    assert extract_possible_location("Fire near welding section 🔥") == "welding section"


def test_full_emergency_flow_order_and_no_model_before_reply(monkeypatch):
    model_calls: list[str] = []

    async def forbidden(*args, **kwargs):
        model_calls.append("call_model")
        raise AssertionError("model_router.call_model must not run on the emergency path")

    monkeypatch.setattr("tools.model_router.call_model", forbidden)
    monkeypatch.setattr("guardrails.emergency_bypass.call_model", forbidden, raising=False)

    orch = _orch()

    async def go():
        result = await orch.process_incoming_whatsapp_message(_msg(text="Fire now 🔥"))
        return result

    result = run(go())
    order = orch.pipeline_trace
    assert result.is_hazard_report is True
    assert order[:5] == [
        "emergency_bypass",
        "emergency_detection",
        "emergency_incident_created",
        "emergency_slack_alert",
        "emergency_worker_reply",
    ]
    if "intake_agent" in order:
        assert order.index("emergency_worker_reply") < order.index("intake_agent")
    assert model_calls == []
    assert live_call_model is not None
    assert len(orch._repo.create_calls) == 1
    created = orch._repo.create_calls[0]
    assert created.hazard_category == "unspecified-emergency"
    assert created.current_risk_level == "Critical"
    assert orch._slack_client.posts
    slack_text = orch._slack_client.posts[0]["text"]
    assert "EMERGENCY ALERT" in slack_text
    assert "Bypassed" in slack_text
    assert orch._whatsapp_transport.payloads
    assert WORKER_EMERGENCY_REPLY["en"] in orch._whatsapp_transport.payloads[0]


def test_async_enrichment_updates_same_incident():
    orch = _orch()

    async def go():
        result = await orch.process_incoming_whatsapp_message(_msg(text="SOS"))
        await orch.wait_for_emergency_enrichment()
        return result

    result = run(go())
    assert len(orch._repo.create_calls) == 1
    assert result.canonical_incident_id == orch._repo.create_calls[0].incident_ref
    assert orch._intake_script.calls
    assert orch._incident_script.calls
    assert orch._repo.field_updates
    kinds = [getattr(item, "update_type", None) for item in orch._repo.updates]
    assert "emergency_bypass" in kinds
    assert "emergency_enrichment_completed" in kinds


def test_duplicate_sos_does_not_create_three_incidents():
    orch = _orch()

    async def go():
        await orch.process_incoming_whatsapp_message(_msg(provider_message_id="wamid.1", text="SOS"))
        await orch.process_incoming_whatsapp_message(_msg(provider_message_id="wamid.2", text="SOS"))
        await orch.process_incoming_whatsapp_message(_msg(provider_message_id="wamid.3", text="SOS"))

    run(go())
    assert len(orch._repo.create_calls) == 1
    kinds = [getattr(item, "update_type", None) for item in orch._repo.updates]
    assert kinds.count("emergency_repeat") == 2


def test_slack_unavailable_still_creates_incident():
    slack = FakeSlackClient()
    slack.fail = "down"
    orch = _orch(slack_client=slack)
    result = run(orch.process_incoming_whatsapp_message(_msg(text="SOS")))
    assert len(orch._repo.create_calls) == 1
    assert result.canonical_incident_id
    assert orch._whatsapp_transport.payloads


def test_whatsapp_unavailable_still_stores_incident():
    whatsapp = RecordingWhatsApp()
    whatsapp.fail = True
    orch = _orch(whatsapp=whatsapp)
    result = run(orch.process_incoming_whatsapp_message(_msg(text="SOS")))
    assert len(orch._repo.create_calls) == 1
    assert result.canonical_incident_id
    assert orch._worker_retry_queue


def test_ai_unavailable_emergency_response_still_completes():
    async def broken_intake(*args, **kwargs):
        raise RuntimeError("model down")

    orch = _orch(intake_fn=broken_intake)

    async def go():
        result = await orch.process_incoming_whatsapp_message(_msg(text="SOS"))
        await orch.wait_for_emergency_enrichment()
        return result

    result = run(go())
    assert len(orch._repo.create_calls) == 1
    assert orch._slack_client.posts
    assert orch._whatsapp_transport.payloads
    assert result.guidance_sent is True


def test_whatsapp_emergency_check_runs_first():
    order: list[str] = []

    class Rec:
        def __init__(self) -> None:
            self.messages = []

        async def process_incoming_whatsapp_message(self, message):
            order.append("orchestrator")
            self.messages.append(message)
            return SimpleNamespace(provider_message_id=message.provider_message_id)

    def emergency(text: str | None) -> bool:
        order.append("emergency")
        return is_emergency_trigger(text)

    handler = SentinelLoopWhatsAppHandler(
        orchestrator=Rec(),
        transport=WhatsAppCloudTransport(client=AsyncMock()),
        skip_kernel_init=True,
        emergency_fn=emergency,
    )
    orch = handler._orchestrator
    run(
        handler.handle_incoming_webhook_message(
            {"id": "wamid.sos", "from": "94771234567", "type": "text", "text": {"body": "SOS"}},
            {},
        )
    )
    assert order == ["emergency", "orchestrator"]
    assert orch.messages[0].emergency_bypass is True


def test_slack_post_error_is_swallowed():
    class Boom(SlackHandler):
        async def post_incident_message(self, **kwargs):
            raise SlackPostError("slack_post_failed", "down")

    orch = _orch()
    orch.slack = Boom(client=FakeSlackClient(), destinations={"Emergency Response Team": "C-EMRG"})
    result = run(orch.process_incoming_whatsapp_message(_msg(text="SOS")))
    assert len(orch._repo.create_calls) == 1
    assert result.canonical_incident_id
