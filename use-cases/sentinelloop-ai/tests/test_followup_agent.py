"""Follow-up verification tests. No live WhatsApp, Slack, or Supabase."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from agents.followup_agent import (
    ERROR_AMBIGUOUS,
    ERROR_DELIVERY,
    ERROR_DUPLICATE,
    ERROR_HUMAN_REVIEW,
    ERROR_NO_WORKER,
    ERROR_REPO,
    ERROR_STALE,
    ERROR_TEAM_NOTIFY,
    ERROR_TRANSITION,
    ERROR_UNSUPPORTED_FILE,
    ERROR_WRONG_THREAD,
    VERIFICATION_CONFIRMED,
    VERIFICATION_PENDING,
    VERIFICATION_STILL_EXISTS,
    VERIFICATION_UNSURE,
    FollowupService,
    MemoryFollowupStore,
    parse_verification_response,
)
from integrations.slack_handler import SlackHandler
from integrations.whatsapp import ACTION_STILL_EXISTS, ACTION_UNSURE, ACTION_YES, WhatsAppHandler, encode_action
from tools.lifecycle import STATUS_CLOSED, STATUS_IN_PROGRESS, STATUS_NEW, STATUS_RESOLVED


def run(coro):
    return asyncio.run(coro)


class FakeWhatsApp:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail = False

    async def __call__(self, payload: dict) -> dict:
        if self.fail:
            raise RuntimeError("whatsapp down")
        self.sent.append(payload)
        return {"ok": True, "id": f"wamid.{len(self.sent)}"}


class FakeSlackClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []
        self.fail = False

    async def chat_postMessage(self, **kwargs):
        if self.fail:
            raise TimeoutError("timeout")
        self.posts.append(kwargs)
        return {"ok": True, "ts": "9.0", "channel": kwargs.get("channel")}


class FakeRepo:
    def __init__(self) -> None:
        self.statuses: list[str] = []
        self.updates: list[object] = []
        self.evidence: list[tuple] = []
        self.fields: list[dict] = []
        self.fail_update = False
        self.incident_status = "RESOLVED"
        self.closed_at = None
        self.reopen_count = 0
        self.risk_level = "Medium"
        self.hazard_category = "electrical"

    def get_incident(self, incident_id):
        return {
            "id": incident_id,
            "status": self.incident_status,
            "closed_at": self.closed_at,
            "reopen_count": self.reopen_count,
            "current_risk_level": self.risk_level,
            "hazard_category": self.hazard_category,
        }

    def update_incident_status(self, incident_id, status):
        if self.fail_update:
            raise RuntimeError("db down")
        self.incident_status = status
        self.statuses.append(status)
        return self.get_incident(incident_id)

    def update_incident_fields(self, incident_id, fields):
        if self.fail_update:
            raise RuntimeError("db down")
        if fields.get("status"):
            self.incident_status = fields["status"]
            self.statuses.append(fields["status"])
        if fields.get("closed_at"):
            self.closed_at = fields["closed_at"]
        if fields.get("reopen_count") is not None:
            self.reopen_count = fields["reopen_count"]
        self.fields.append(fields)
        return self.get_incident(incident_id)

    def add_update(self, data):
        if self.fail_update:
            raise RuntimeError("db down")
        self.updates.append(data)
        return data

    def add_evidence(self, file, incident_id, stage, *, metadata=None, filename=None, content_type=None):
        self.evidence.append((file, incident_id, stage, metadata, filename, content_type))
        return {"id": uuid4(), "stage": stage}


def _incident(**kwargs) -> dict:
    base = {
        "incident_ref": "INC-0042",
        "id": str(uuid4()),
        "status": STATUS_RESOLVED,
        "worker_phone": "94770000000",
        "detected_language": "en",
        "location": "Electrical Room",
        "assigned_team": "Electrical Maintenance",
        "slack_channel_id": "C-ELEC",
        "slack_thread_ts": "1.000",
        "hazard_category": "electrical",
        "risk_level": "Medium",
    }
    base.update(kwargs)
    return base


def _service(whatsapp: FakeWhatsApp | None = None, slack: FakeSlackClient | None = None, repo: FakeRepo | None = None):
    wa = whatsapp or FakeWhatsApp()
    sl = slack or FakeSlackClient()
    return (
        FollowupService(
            whatsapp=WhatsAppHandler(client=wa),
            slack=SlackHandler(client=sl),
            repository=repo,
            store=MemoryFollowupStore(),
        ),
        wa,
        sl,
    )


def test_parse_english_aliases():
    assert parse_verification_response("Yes") == VERIFICATION_CONFIRMED
    assert parse_verification_response("safe") == VERIFICATION_CONFIRMED
    assert parse_verification_response("No, still exists") == VERIFICATION_STILL_EXISTS
    assert parse_verification_response("still dangerous") == VERIFICATION_STILL_EXISTS
    assert parse_verification_response("Not sure") == VERIFICATION_UNSURE
    assert parse_verification_response("maybe") is None


def test_parse_localized_options():
    assert parse_verification_response("ඔව්", "si") == VERIFICATION_CONFIRMED
    assert parse_verification_response("ஆம்", "ta") == VERIFICATION_CONFIRMED
    assert parse_verification_response("නැහැ, තවම තියෙනවා", "si") == VERIFICATION_STILL_EXISTS
    assert parse_verification_response("உறுதியில்லை", "ta") == VERIFICATION_UNSURE


def test_resolved_sends_verification_in_worker_language():
    service, wa, _ = _service()
    result = run(service.start_worker_verification(_incident(detected_language="si")))
    assert result.worker_notified is True
    assert result.verification_status == VERIFICATION_PENDING
    assert result.error is None
    assert wa.sent[0]["type"] == "interactive"
    body = wa.sent[0]["interactive"]["body"]["text"]
    assert "ආරක්ෂිතද" in body
    ids = [b["reply"]["id"] for b in wa.sent[0]["interactive"]["action"]["buttons"]]
    assert any(ACTION_YES in item for item in ids)
    assert any(ACTION_STILL_EXISTS in item for item in ids)
    assert any(ACTION_UNSURE in item for item in ids)


def test_tamil_verification_semantics():
    service, wa, _ = _service()
    run(service.start_worker_verification(_incident(detected_language="ta")))
    titles = [b["reply"]["title"] for b in wa.sent[0]["interactive"]["action"]["buttons"]]
    assert "ஆம்" in titles
    assert any("இன்னும்" in title for title in titles)
    assert "உறுதியில்லை" in titles


def test_yes_closes_and_records_timestamp():
    repo = FakeRepo()
    service, _, slack = _service(repo=repo)
    incident = _incident()
    run(service.start_worker_verification(incident))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert result.closed is True
    assert result.status == STATUS_CLOSED
    assert result.resolution_timestamp is not None
    assert repo.incident_status == "CLOSED"
    assert repo.closed_at is not None
    assert any("Closed" in str(post.get("text")) for post in slack.posts)


def test_still_exists_reopens_same_incident_and_renotifies():
    repo = FakeRepo()
    service, _, slack = _service(repo=repo)
    run(service.start_worker_verification(_incident()))
    result = run(service.handle_worker_verification_response(text="No, still exists", incident_id="INC-0042"))
    assert result.reopened is True
    assert result.status == STATUS_IN_PROGRESS
    assert result.incident_id == "INC-0042"
    assert result.team_renotified is True
    assert repo.incident_status == "IN_PROGRESS"
    assert repo.reopen_count == 1
    blob = slack.posts[0]["text"]
    assert "still exists" in blob.lower() or "verification failed" in blob.lower()
    assert "Electrical Maintenance" in blob
    assert slack.posts[0]["thread_ts"] == "1.000"
    assert slack.posts[0]["channel"] == "C-ELEC"
    types = [getattr(u, "update_type", None) for u in repo.updates]
    assert "incident_reopened" in types
    assert repo.risk_level == "Medium"
    assert repo.hazard_category == "electrical"


def test_not_sure_does_not_close():
    repo = FakeRepo()
    service, _, slack = _service(repo=repo)
    run(service.start_worker_verification(_incident()))
    result = run(service.handle_worker_verification_response(text="Not sure", incident_id="INC-0042"))
    assert result.closed is False
    assert result.reopened is False
    assert result.verification_status == VERIFICATION_UNSURE
    assert result.status == STATUS_RESOLVED
    assert repo.incident_status == "RESOLVED"
    assert any("pending" in str(post.get("text")).lower() for post in slack.posts)


def test_ambiguous_reply_clarifies():
    service, wa, _ = _service()
    run(service.start_worker_verification(_incident()))
    result = run(service.handle_worker_verification_response(text="maybe", incident_id="INC-0042"))
    assert result.error == ERROR_AMBIGUOUS
    assert result.closed is False
    assert any(item.get("type") == "text" for item in wa.sent)
    assert "Yes" in wa.sent[-1]["text"]["body"]


def test_interactive_ids_are_language_independent():
    service, _, _ = _service()
    run(service.start_worker_verification(_incident(detected_language="si")))
    result = run(
        service.handle_worker_verification_response(
            action_id=encode_action(ACTION_YES, "INC-0042", 1),
            incident_id="INC-0042",
        )
    )
    assert result.status == STATUS_CLOSED


def test_after_photo_uses_repository_add_evidence():
    repo = FakeRepo()
    service, _, _ = _service(repo=repo)
    incident = _incident()
    run(service.start_worker_verification(incident))
    photo = run(
        service.handle_after_photo(
            incident_id="INC-0042",
            content=b"jpeg-bytes",
            filename="after.jpg",
            content_type="image/jpeg",
            slack_file_id="F1",
            thread_ts="1.000",
            channel_id="C-ELEC",
            actor="U1",
        )
    )
    assert photo.after_evidence_added is True
    assert repo.evidence
    _file, _id, stage, metadata, filename, content_type = repo.evidence[0]
    assert stage == "verification"
    assert metadata.evidence_type == "after"
    assert filename == "after.jpg"
    closed = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert closed.closed is True
    assert closed.after_evidence_added is True


def test_no_after_photo_still_closes():
    service, _, _ = _service(repo=FakeRepo())
    run(service.start_worker_verification(_incident()))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert result.closed is True


def test_duplicate_after_photo():
    repo = FakeRepo()
    service, _, _ = _service(repo=repo)
    run(service.start_worker_verification(_incident()))
    kwargs = dict(
        incident_id="INC-0042",
        content=b"jpeg-bytes",
        filename="after.jpg",
        content_type="image/jpeg",
        slack_file_id="F1",
        thread_ts="1.000",
        channel_id="C-ELEC",
    )
    run(service.handle_after_photo(**kwargs))
    again = run(service.handle_after_photo(**kwargs))
    assert again.error == ERROR_DUPLICATE
    assert len(repo.evidence) == 1


def test_wrong_thread_photo_rejected():
    service, _, _ = _service(repo=FakeRepo())
    run(service.start_worker_verification(_incident()))
    result = run(
        service.handle_after_photo(
            incident_id="INC-0042",
            content=b"jpeg-bytes",
            content_type="image/jpeg",
            slack_file_id="F9",
            thread_ts="unrelated",
            channel_id="C-ELEC",
        )
    )
    assert result.error == ERROR_WRONG_THREAD


def test_non_image_attachment_rejected():
    service, _, _ = _service(repo=FakeRepo())
    run(service.start_worker_verification(_incident()))
    result = run(
        service.handle_after_photo(
            incident_id="INC-0042",
            content=b"%PDF",
            content_type="application/pdf",
            slack_file_id="Fpdf",
            thread_ts="1.000",
            channel_id="C-ELEC",
        )
    )
    assert result.error == ERROR_UNSUPPORTED_FILE


def test_duplicate_resolved_event_sends_once():
    service, wa, _ = _service()
    incident = _incident()
    first = run(service.start_worker_verification(incident, event_id="ev-1"))
    second = run(service.start_worker_verification(incident, event_id="ev-1"))
    third = run(service.start_worker_verification(incident, event_id="ev-2"))
    assert first.worker_notified is True
    assert second.error == ERROR_DUPLICATE
    assert third.error == ERROR_DUPLICATE
    assert len(wa.sent) == 1


def test_whatsapp_retry_mutates_once():
    repo = FakeRepo()
    service, _, _ = _service(repo=repo)
    run(service.start_worker_verification(_incident()))
    first = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042", event_id="wamid.1"))
    second = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042", event_id="wamid.1"))
    assert first.closed is True
    assert second.error == ERROR_DUPLICATE
    assert repo.statuses.count("CLOSED") == 1


def test_stale_yes_after_reopen_does_not_close():
    service, _, _ = _service(repo=FakeRepo())
    run(service.start_worker_verification(_incident()))
    run(service.reopen_incident("INC-0042"))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert result.closed is False
    assert result.error == ERROR_STALE
    assert service.store.get("INC-0042").status == STATUS_IN_PROGRESS


def test_stale_no_from_old_cycle():
    service, _, _ = _service(repo=FakeRepo())
    run(service.start_worker_verification(_incident()))
    run(service.reopen_incident("INC-0042"))
    run(service.start_worker_verification(_incident()))
    result = run(
        service.handle_worker_verification_response(
            action_id=encode_action(ACTION_STILL_EXISTS, "INC-0042", 1),
            incident_id="INC-0042",
        )
    )
    assert result.error == ERROR_STALE
    assert result.reopened is False


def test_closed_late_reply_ignored():
    service, _, _ = _service(repo=FakeRepo())
    run(service.start_worker_verification(_incident()))
    run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    late = run(service.handle_worker_verification_response(text="No", incident_id="INC-0042"))
    assert late.error == ERROR_STALE
    assert service.store.get("INC-0042").status == STATUS_CLOSED


def test_yes_without_verification_context():
    service, _, _ = _service()
    result = run(service.handle_worker_verification_response(text="Yes", worker_phone="94770000000"))
    assert result.error == ERROR_STALE
    assert result.closed is False


def test_multiple_incidents_use_action_context():
    service, _, _ = _service(repo=FakeRepo())
    run(service.start_worker_verification(_incident(incident_ref="INC-1", worker_phone="9477")))
    run(service.start_worker_verification(_incident(incident_ref="INC-2", worker_phone="9477")))
    result = run(
        service.handle_worker_verification_response(
            action_id=encode_action(ACTION_YES, "INC-2", 1),
            worker_phone="9477",
        )
    )
    assert result.incident_id == "INC-2"
    assert result.closed is True
    assert service.store.get("INC-1").status == STATUS_RESOLVED


def test_repository_failure_on_close():
    repo = FakeRepo()
    service, _, _ = _service(repo=repo)
    run(service.start_worker_verification(_incident()))
    repo.fail_update = True
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert result.error == ERROR_REPO
    assert result.closed is False
    assert service.store.get("INC-0042").status == STATUS_RESOLVED


def test_repository_failure_on_reopen():
    repo = FakeRepo()
    service, _, slack = _service(repo=repo)
    run(service.start_worker_verification(_incident()))
    repo.fail_update = True
    result = run(service.handle_worker_verification_response(text="No, still exists", incident_id="INC-0042"))
    assert result.error == ERROR_REPO
    assert result.reopened is False
    assert not slack.posts


def test_slack_failure_after_reopen_keeps_in_progress():
    repo = FakeRepo()
    slack = FakeSlackClient()
    slack.fail = True
    service, _, _ = _service(slack=slack, repo=repo)
    run(service.start_worker_verification(_incident()))
    result = run(service.handle_worker_verification_response(text="No, still exists", incident_id="INC-0042"))
    assert result.reopened is True
    assert result.status == STATUS_IN_PROGRESS
    assert result.error == ERROR_TEAM_NOTIFY
    assert repo.incident_status == "IN_PROGRESS"


def test_whatsapp_send_failure_does_not_close():
    wa = FakeWhatsApp()
    wa.fail = True
    service, _, _ = _service(whatsapp=wa, repo=FakeRepo())
    result = run(service.start_worker_verification(_incident()))
    assert result.worker_notified is False
    assert result.error == ERROR_DELIVERY
    assert result.closed is False
    assert result.status == STATUS_RESOLVED


def test_missing_worker_identity():
    service, wa, _ = _service()
    result = run(service.start_worker_verification(_incident(worker_phone=None, reporter_id=None)))
    assert result.error == ERROR_NO_WORKER
    assert wa.sent == []


def test_invalid_status_guard():
    from agents.followup_agent import FollowupRecord

    service, _, _ = _service()
    service.store.put(
        FollowupRecord(incident_id="INC-NEW", status=STATUS_NEW, verification_status=VERIFICATION_PENDING)
    )
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-NEW"))
    assert result.error in {ERROR_STALE, ERROR_TRANSITION}
    assert result.closed is False


def test_second_resolution_cycle():
    repo = FakeRepo()
    service, wa, _ = _service(repo=repo)
    incident = _incident()
    run(service.start_worker_verification(incident, event_id="r1"))
    run(service.handle_worker_verification_response(text="No, still exists", incident_id="INC-0042"))
    again = run(service.start_worker_verification(incident, event_id="r2"))
    assert again.verification_cycle == 2
    assert len(wa.sent) == 2
    closed = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert closed.closed is True
    assert closed.verification_cycle == 2


def test_assigned_team_not_remapped():
    service, _, slack = _service(repo=FakeRepo())
    run(
        service.start_worker_verification(_incident(assigned_team="Electrical Maintenance", hazard_category="chemical"))
    )
    run(service.handle_worker_verification_response(text="No, still exists", incident_id="INC-0042"))
    assert "Electrical Maintenance" in slack.posts[0]["text"]
    assert "Lab Safety" not in slack.posts[0]["text"]


def test_high_worker_yes_requires_human_slack_close():
    repo = FakeRepo()
    repo.risk_level = "High"
    service, _, slack = _service(repo=repo)
    run(service.start_worker_verification(_incident(risk_level="High")))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert result.closed is False
    assert result.error == ERROR_HUMAN_REVIEW
    assert repo.incident_status == "RESOLVED"
    assert any("SPEC.md" in str(post.get("text")) for post in slack.posts)


def test_critical_worker_yes_requires_human_slack_close():
    repo = FakeRepo()
    repo.risk_level = "Critical"
    service, _, _ = _service(repo=repo)
    run(service.start_worker_verification(_incident(risk_level="Critical")))
    result = run(service.handle_worker_verification_response(text="Yes", incident_id="INC-0042"))
    assert result.closed is False
    assert result.error == ERROR_HUMAN_REVIEW


def test_high_slack_closed_allows_closure():
    repo = FakeRepo()
    repo.risk_level = "High"
    service, _, _ = _service(repo=repo)
    run(service.start_worker_verification(_incident(risk_level="High")))
    result = run(
        service.confirm_safe_and_close(
            "INC-0042",
            actor="U12345",
            source="slack",
            slack_closure={
                "closed_by": "U12345",
                "source": "slack",
                "action": "Closed",
                "timestamp": "2026-08-31T12:00:00+00:00",
                "slack_action_id": "incident_closed",
            },
        )
    )
    assert result.closed is True
    assert result.status == STATUS_CLOSED
