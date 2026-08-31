"""WhatsApp transport tests. No live Meta calls."""

from __future__ import annotations

import asyncio
import hashlib
import hmac

import pytest

from integrations.whatsapp import WhatsAppSendError
from integrations.whatsapp_handler import (
    SentinelLoopWhatsAppHandler,
    WhatsAppCloudTransport,
    extract_reply_context,
    normalize_incoming_message,
    verify_webhook_challenge,
    verify_webhook_request,
)


def run(coro):
    return asyncio.run(coro)


def test_normalize_text_message():
    message = {
        "id": "wamid.1",
        "from": "94771234567",
        "type": "text",
        "timestamp": "1710000000",
        "text": {"body": "The electrical panel is sparking."},
    }
    normalized = normalize_incoming_message(message)
    assert normalized is not None
    assert normalized.provider_message_id == "wamid.1"
    assert normalized.sender_id == "94771234567"
    assert normalized.message_type == "text"
    assert normalized.text == "The electrical panel is sparking."
    assert normalized.media is None


def test_normalize_image_with_caption():
    message = {
        "id": "wamid.img",
        "from": "94771234567",
        "type": "image",
        "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "caption": "oil leak near machine 4"},
    }
    normalized = normalize_incoming_message(message)
    assert normalized is not None
    assert normalized.caption == "oil leak near machine 4"
    assert normalized.text == "oil leak near machine 4"
    assert normalized.media is not None
    assert normalized.media.media_id == "MEDIA1"
    assert normalized.media.provider_reference == "MEDIA1"
    assert normalized.media.filename is None


def test_normalize_image_only():
    message = {
        "id": "wamid.img2",
        "from": "94771234567",
        "type": "image",
        "image": {"id": "MEDIA2", "mime_type": "image/png"},
    }
    normalized = normalize_incoming_message(message)
    assert normalized is not None
    assert normalized.caption is None
    assert normalized.text is None
    assert normalized.media is not None
    assert normalized.media.media_id == "MEDIA2"


def test_extract_reply_context():
    message = {
        "id": "wamid.2",
        "from": "9477",
        "type": "text",
        "text": {"body": "Packing Area 3"},
        "context": {"id": "wamid.question"},
    }
    assert extract_reply_context(message) == "wamid.question"
    normalized = normalize_incoming_message(message)
    assert normalized is not None
    assert normalized.reply_to_message_id == "wamid.question"


def test_unsupported_types_do_not_raise():
    for kind in ("audio", "video", "sticker", "document", "location", "reaction"):
        normalized = normalize_incoming_message({"id": f"wamid.{kind}", "from": "9477", "type": kind})
        assert normalized is not None
        assert normalized.supported is False


def test_malformed_message_returns_none():
    assert normalize_incoming_message({"type": "text"}) is None
    assert normalize_incoming_message(None) is None


def test_verify_webhook_challenge():
    assert verify_webhook_challenge("subscribe", "secret", "12345", "secret") == "12345"
    assert verify_webhook_challenge("subscribe", "wrong", "12345", "secret") is None


def test_verify_webhook_signature():
    secret = "app-secret"
    body = b'{"object":"whatsapp_business_account"}'
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_request(body, f"sha256={digest}", secret) is True
    assert verify_webhook_request(body, "sha256=deadbeef", secret) is False
    assert verify_webhook_request(body, None, None) is True


class RecordingClient:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.fail = False

    async def __call__(self, payload):
        if self.fail:
            raise RuntimeError("graph down")
        self.payloads.append(payload)
        return {"messages": [{"id": f"wamid.out.{len(self.payloads)}"}]}


def test_send_text_and_clarification_and_guidance():
    client = RecordingClient()
    transport = WhatsAppCloudTransport(client)
    sent = run(transport.send_text_message("9477", "hello"))
    assert sent["id"] == "wamid.out.1"
    run(transport.send_clarification("9477", "Where is this hazard?"))
    run(transport.send_guidance("9477", "Stay back from the panel."))
    assert len(client.payloads) == 3
    assert client.payloads[1]["text"]["body"] == "Where is this hazard?"


def test_send_interactive_message():
    client = RecordingClient()
    transport = WhatsAppCloudTransport(client)
    run(
        transport.send_interactive_message(
            "9477", "Is the area safe?", [{"id": "verification_yes:INC-1:1", "title": "Yes"}]
        )
    )
    assert client.payloads[0]["type"] == "interactive"


def test_provider_api_error():
    client = RecordingClient()
    client.fail = True
    transport = WhatsAppCloudTransport(client)
    with pytest.raises(WhatsAppSendError):
        run(transport.send_text_message("9477", "hello"))


def test_resolve_inbound_media_injected():
    async def media_client(op, media_id):
        assert op == "download"
        return {"content": b"\xff\xd8fake", "mime_type": "image/jpeg"}

    transport = WhatsAppCloudTransport(media_client=media_client)
    resolved = run(transport.resolve_inbound_media({"media_id": "MEDIA1", "mime_type": "image/jpeg"}))
    assert resolved is not None
    assert resolved.content.startswith(b"\xff\xd8")
    assert resolved.error is None


def test_reject_non_image_media():
    transport = WhatsAppCloudTransport()
    resolved = run(
        transport.resolve_inbound_media({"media_id": "X", "mime_type": "application/x-msdownload", "content": b"MZ"})
    )
    assert resolved is not None
    assert resolved.error == "unsupported_media_type"


def test_handler_unsupported_sticker_does_not_crash():
    client = RecordingClient()
    transport = WhatsAppCloudTransport(client)
    handler = SentinelLoopWhatsAppHandler(orchestrator=None, transport=transport, skip_kernel_init=True)

    class NoOpOrch:
        async def process_incoming_whatsapp_message(self, message):
            return {"unsupported": True, "provider_message_id": message.provider_message_id}

    handler._orchestrator = NoOpOrch()
    result = run(handler.handle_incoming_webhook({"id": "wamid.sticker", "from": "9477", "type": "sticker"}, {}))
    assert result["unsupported"] is True
    assert client.payloads


def test_duplicate_provider_event_is_not_text_keyed():
    first = normalize_incoming_message(
        {"id": "wamid.a", "from": "9477", "type": "text", "text": {"body": "wire sparking"}}
    )
    second = normalize_incoming_message(
        {"id": "wamid.b", "from": "9477", "type": "text", "text": {"body": "wire sparking"}}
    )
    assert first is not None and second is not None
    assert first.provider_message_id != second.provider_message_id
    assert first.text == second.text
