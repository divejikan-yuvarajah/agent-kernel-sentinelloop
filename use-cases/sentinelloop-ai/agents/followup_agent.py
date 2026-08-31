"""SentinelLoop follow-up agent.

Owns worker verification after an officer marks an incident Resolved.
Does not reclassify hazards, recalculate risk, or invent safety guidance.
Repository state is authoritative. Closed requires valid worker confirmation.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from integrations.slack_handler import (
    IMAGE_CONTENT_TYPES,
    SlackHandler,
    SlackPostError,
    extract_slack_file,
)
from integrations.telegram_handler import SESSION_PREFIX, TelegramSendError
from integrations.whatsapp import (
    ACTION_STILL_EXISTS,
    ACTION_UNSURE,
    ACTION_YES,
    WhatsAppHandler,
    WhatsAppSendError,
    encode_action,
    extract_interactive_reply,
    parse_action_id,
)
from tools.lifecycle import (
    LIFECYCLE,
    STATUS_AWAITING_VERIFICATION,
    STATUS_CLOSED,
    STATUS_IN_PROGRESS,
    STATUS_RESOLVED,
    can_transition,
    to_display_status,
    to_repository_status,
    validate_status_transition,
)

log = logging.getLogger("sentinelloop.followup")

VERIFICATION_PENDING = "pending"
VERIFICATION_CONFIRMED = "confirmed_safe"
VERIFICATION_STILL_EXISTS = "still_exists"
VERIFICATION_UNSURE = "unsure"

ERROR_NOT_FOUND = "incident_not_found"
ERROR_NO_WORKER = "worker_identity_missing"
ERROR_DELIVERY = "verification_delivery_failed"
ERROR_REPO = "repository_update_failed"
ERROR_STALE = "stale_verification_response"
ERROR_TRANSITION = "invalid_status_transition"
ERROR_EVIDENCE = "after_evidence_add_failed"
ERROR_DUPLICATE = "duplicate_verification_event"
ERROR_AMBIGUOUS = "verification_ambiguous"
ERROR_TEAM_NOTIFY = "team_renotification_failed"
ERROR_WRONG_THREAD = "unrelated_slack_thread"
ERROR_UNSUPPORTED_FILE = "unsupported_evidence_type"
ERROR_HUMAN_REVIEW = "human_review_required"

_PUNCT_RE = re.compile(r"[!?.,;:]+")

VERIFICATION_PROMPT = {
    "en": ("The reported hazard has been marked resolved. " "Can you confirm that the area is now safe?"),
    "si": "වාර්තා කළ අනතුරුදායක තත්ත්වය විසඳා ඇති බව සලකුණු කර ඇත. එම ස්ථානය දැන් ආරක්ෂිතද?",
    "ta": "புகாரளிக்கப்பட்ட ஆபத்து தீர்க்கப்பட்டதாக குறிக்கப்பட்டுள்ளது. அந்த இடம் இப்போது பாதுகாப்பானதா?",
}

CLARIFICATION_PROMPT = {
    "en": "Please choose: Yes / No, still exists / Not sure",
    "si": "කරුණාකර තෝරන්න: ඔව් / නැහැ, තවම තියෙනවා / විශ්වාස නැහැ",
    "ta": "தயவுசெய்து தேர்வு செய்யவும்: ஆம் / இல்லை, இன்னும் உள்ளது / உறுதியில்லை",
}

VERIFICATION_OPTIONS = {
    VERIFICATION_CONFIRMED: {"en": "Yes", "si": "ඔව්", "ta": "ஆம்"},
    VERIFICATION_STILL_EXISTS: {
        "en": "No, still exists",
        "si": "නැහැ, තවම තියෙනවා",
        "ta": "இல்லை, இன்னும் உள்ளது",
    },
    VERIFICATION_UNSURE: {"en": "Not sure", "si": "විශ්වාස නැහැ", "ta": "உறுதியில்லை"},
}

_CONFIRMED_ALIASES = {
    "yes",
    "y",
    "safe",
    "it is safe",
    "its safe",
    "it's safe",
    "fixed",
    "okay now",
    "ok now",
    "ok",
    "ඔව්",
    "ஆம்",
}
_STILL_ALIASES = {
    "no",
    "still there",
    "still exists",
    "no still exists",
    "no, still exists",
    "not fixed",
    "still dangerous",
    "problem remains",
    "නැහැ",
    "නැහැ තවම තියෙනවා",
    "නැහැ, තවම තියෙනවා",
    "இல்லை",
    "இல்லை இன்னும் உள்ளது",
    "இல்லை, இன்னும் உள்ளது",
}
_UNSURE_ALIASES = {
    "not sure",
    "unsure",
    "don't know",
    "dont know",
    "cannot confirm",
    "can't confirm",
    "විශ්වාස නැහැ",
    "உறுதியில்லை",
}


class FollowupResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    incident_id: str | None = None
    previous_status: str | None = None
    status: str | None = None
    verification_status: str | None = None
    verification_cycle: int | None = None
    worker_language: str | None = None
    worker_notified: bool = False
    team_renotified: bool = False
    reopened: bool = False
    closed: bool = False
    after_evidence_added: bool = False
    resolution_timestamp: str | None = None
    requires_risk_reassessment: bool = False
    error: str | None = None
    worker_reply: str | None = None


class FollowupRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    incident_id: str
    uuid: str | None = None
    worker_phone: str | None = None
    worker_language: str | None = None
    status: str = STATUS_RESOLVED
    verification_status: str = VERIFICATION_PENDING
    verification_cycle: int = 1
    assigned_team: str | None = None
    slack_channel_id: str | None = None
    slack_thread_ts: str | None = None
    location: str | None = None
    hazard_category: str | None = None
    risk_level: str | None = None
    processed_events: list[str] = Field(default_factory=list)
    processed_file_ids: list[str] = Field(default_factory=list)
    pending_after_file_ids: list[str] = Field(default_factory=list)
    reopen_count: int = 0
    reviewed_by_human: bool = False
    slack_closed_action: dict[str, Any] | None = None


class MemoryFollowupStore:
    def __init__(self) -> None:
        self.records: dict[str, FollowupRecord] = {}
        self.by_phone: dict[str, list[str]] = {}

    def get(self, incident_id: str) -> FollowupRecord | None:
        return self.records.get(incident_id)

    def put(self, record: FollowupRecord) -> FollowupRecord:
        self.records[record.incident_id] = record
        if record.worker_phone:
            bucket = self.by_phone.setdefault(record.worker_phone, [])
            if record.incident_id not in bucket:
                bucket.append(record.incident_id)
        return record

    def pending_for_worker(self, phone: str) -> list[FollowupRecord]:
        ids = self.by_phone.get(phone) or []
        return [
            self.records[i]
            for i in ids
            if i in self.records and self.records[i].verification_status in {VERIFICATION_PENDING, VERIFICATION_UNSURE}
        ]


def parse_verification_response(text: str | None, language: str | None = None) -> str | None:
    if not text:
        return None
    normalized = _PUNCT_RE.sub("", str(text).strip().lower())
    normalized = " ".join(normalized.split())
    if not normalized:
        return None
    if normalized in _CONFIRMED_ALIASES:
        return VERIFICATION_CONFIRMED
    if normalized in _STILL_ALIASES:
        return VERIFICATION_STILL_EXISTS
    if normalized in _UNSURE_ALIASES:
        return VERIFICATION_UNSURE
    lang = _language(language)
    for result, labels in VERIFICATION_OPTIONS.items():
        label = _PUNCT_RE.sub("", labels.get(lang, labels["en"]).strip().lower())
        if normalized == label:
            return result
    return None


def _language(value: str | None) -> str:
    raw = (value or "en").strip().lower()
    if raw in {"si", "sinhala", "sin"}:
        return "si"
    if raw in {"ta", "tamil"}:
        return "ta"
    if raw in {"en", "english"}:
        return "en"
    if raw in {"mixed"}:
        return "en"
    return "en"


def _option_label(result: str, language: str) -> str:
    labels = VERIFICATION_OPTIONS[result]
    return labels.get(language) or labels["en"]


def build_verification_message(
    *,
    language: str | None,
    incident_id: str | None = None,
    location: str | None = None,
    resolution_summary: str | None = None,
) -> str:
    lang = _language(language)
    prompt = VERIFICATION_PROMPT.get(lang) or VERIFICATION_PROMPT["en"]
    parts: list[str] = []
    if incident_id:
        loc = f" at {location}" if location else ""
        if lang == "si":
            parts.append(f"සිද්ධිය {incident_id}{loc} විසඳා ඇති බව සලකුණු කර ඇත.")
        elif lang == "ta":
            parts.append(f"சம்பவம் {incident_id}{loc} தீர்க்கப்பட்டதாக குறிக்கப்பட்டுள்ளது.")
        else:
            parts.append(f"Incident {incident_id}{loc} was marked resolved.")
    parts.append(prompt)
    if resolution_summary:
        parts.append(str(resolution_summary).strip())
    return "\n\n".join(part for part in parts if part)


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, dict):
            return data
    return {}


def _incident_key(mapping: dict[str, Any]) -> str | None:
    for key in ("incident_ref", "incident_id"):
        value = mapping.get(key)
        if value:
            return str(value)
    return None


def _worker_phone(mapping: dict[str, Any]) -> str | None:
    for key in ("worker_phone", "reporter_id", "from", "phone"):
        value = mapping.get(key)
        if value:
            return str(value)
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_verification_context(record: FollowupRecord, *, cycle: int | None = None) -> str | None:
    if record.status == STATUS_CLOSED:
        return ERROR_STALE
    if record.verification_status not in {VERIFICATION_PENDING, VERIFICATION_UNSURE}:
        return ERROR_STALE
    if record.status not in {STATUS_RESOLVED, STATUS_AWAITING_VERIFICATION}:
        return ERROR_STALE
    if cycle is not None and cycle != record.verification_cycle:
        return ERROR_STALE
    return None


class FollowupService:
    def __init__(
        self,
        *,
        whatsapp: WhatsAppHandler | None = None,
        telegram: Any | None = None,
        slack: SlackHandler | None = None,
        repository: Any | None = None,
        store: MemoryFollowupStore | None = None,
    ) -> None:
        self.whatsapp = whatsapp or WhatsAppHandler()
        self.telegram = telegram
        self.slack = slack or SlackHandler()
        self.repository = repository
        self.store = store or MemoryFollowupStore()

    def _record(self, incident_id: str) -> FollowupRecord:
        found = self.store.get(incident_id)
        if found:
            return found
        return FollowupRecord(incident_id=incident_id)

    def _is_telegram_worker(self, identity: str | None) -> bool:
        return bool(identity) and str(identity).startswith(SESSION_PREFIX)

    def _telegram_transport(self) -> Any:
        if self.telegram is None:
            from integrations.telegram_handler import TelegramTransport

            self.telegram = TelegramTransport()
        return self.telegram

    def _event_seen(self, record: FollowupRecord, event_id: str | None) -> bool:
        return bool(event_id) and event_id in record.processed_events

    def _mark_event(self, record: FollowupRecord, event_id: str | None) -> None:
        if not event_id or event_id in record.processed_events:
            return
        record.processed_events.append(event_id)
        if len(record.processed_events) > 200:
            record.processed_events = record.processed_events[-200:]
        self.store.put(record)

    def _reload_status(self, record: FollowupRecord) -> FollowupRecord:
        if self.repository is None or not record.uuid:
            return record
        try:
            incident = self.repository.get_incident(UUID(record.uuid))
        except Exception:
            return record
        if incident is None:
            return record
        mapping = _as_mapping(incident)
        display = to_display_status(mapping.get("status"))
        if display:
            record.status = display
        if mapping.get("reopen_count") is not None:
            try:
                record.reopen_count = int(mapping["reopen_count"])
            except (TypeError, ValueError):
                pass
        return record

    def _persist(
        self,
        record: FollowupRecord,
        *,
        event_type: str,
        previous_status: str | None,
        actor: str | None,
        source: str,
        extra: dict[str, Any] | None = None,
        timestamps: dict[str, Any] | None = None,
    ) -> None:
        if self.repository is None or not record.uuid:
            return
        incident_uuid = UUID(record.uuid)
        from database.schemas import IncidentUpdateCreate

        fields: dict[str, Any] = {"status": to_repository_status(record.status)}
        if timestamps:
            fields.update(timestamps)
        extras = extra or {}
        if "reopen_count" in extras:
            fields["reopen_count"] = extras["reopen_count"]
        updater = getattr(self.repository, "update_incident_fields", None)
        if callable(updater):
            updater(incident_uuid, fields)
        else:
            self.repository.update_incident_status(incident_uuid, fields["status"])
        self.repository.add_update(
            IncidentUpdateCreate(
                incident_id=incident_uuid,
                update_type=event_type,
                previous_status=previous_status,
                new_status=record.status,
                actor_type="worker" if source == "whatsapp" else "safety_officer",
                actor_reference=actor,
                metadata={
                    "source": source,
                    "verification_status": record.verification_status,
                    "verification_cycle": record.verification_cycle,
                    **(extra or {}),
                },
            )
        )

    async def start_worker_verification(
        self,
        incident: Any,
        *,
        event_id: str | None = None,
        actor: str | None = None,
    ) -> FollowupResult:
        mapping = _as_mapping(incident)
        incident_id = _incident_key(mapping)
        if not incident_id:
            return FollowupResult(error=ERROR_NOT_FOUND)
        log.info("worker_verification_started incident=%s", incident_id)
        existing = self.store.get(incident_id)
        record = existing if existing is not None else FollowupRecord(incident_id=incident_id)
        if mapping.get("id"):
            record.uuid = str(mapping["id"])
        record.worker_phone = _worker_phone(mapping) or record.worker_phone
        record.worker_language = mapping.get("detected_language") or mapping.get("language") or record.worker_language
        record.assigned_team = mapping.get("assigned_team") or record.assigned_team
        record.slack_channel_id = mapping.get("slack_channel_id") or record.slack_channel_id
        record.slack_thread_ts = mapping.get("slack_thread_ts") or record.slack_thread_ts
        record.location = mapping.get("location") or record.location
        record.hazard_category = mapping.get("hazard_category") or record.hazard_category
        record.risk_level = mapping.get("risk_level") or record.risk_level
        incoming_status = to_display_status(mapping.get("status")) or STATUS_RESOLVED
        if incoming_status not in {STATUS_RESOLVED, STATUS_AWAITING_VERIFICATION}:
            incoming_status = STATUS_RESOLVED
        record.status = incoming_status
        if self._event_seen(record, event_id):
            log.info("duplicate_verification_event_ignored")
            return FollowupResult(
                incident_id=incident_id,
                status=record.status,
                verification_status=record.verification_status,
                verification_cycle=record.verification_cycle,
                error=ERROR_DUPLICATE,
            )
        already_pending = (
            existing is not None
            and existing.verification_status in {VERIFICATION_PENDING, VERIFICATION_UNSURE}
            and existing.worker_phone == record.worker_phone
        )
        if existing is not None and existing.verification_status == VERIFICATION_STILL_EXISTS:
            record.verification_cycle = existing.verification_cycle + 1
            already_pending = False
        record.verification_status = VERIFICATION_PENDING
        self.store.put(record)
        if already_pending:
            log.info("duplicate_verification_event_ignored")
            self._mark_event(record, event_id)
            return FollowupResult(
                incident_id=incident_id,
                status=record.status,
                verification_status=VERIFICATION_PENDING,
                verification_cycle=record.verification_cycle,
                worker_language=record.worker_language,
                worker_notified=False,
                error=ERROR_DUPLICATE,
            )
        if not record.worker_phone:
            log.warning("worker_verification_delivery_failed reason=missing_identity")
            return FollowupResult(
                incident_id=incident_id,
                status=record.status,
                verification_status=VERIFICATION_PENDING,
                verification_cycle=record.verification_cycle,
                error=ERROR_NO_WORKER,
            )
        body = build_verification_message(
            language=record.worker_language,
            incident_id=incident_id,
            location=record.location,
            resolution_summary=mapping.get("resolution_summary"),
        )
        lang = _language(record.worker_language)
        buttons = [
            {
                "id": encode_action(ACTION_YES, incident_id, record.verification_cycle),
                "title": _option_label(VERIFICATION_CONFIRMED, lang),
            },
            {
                "id": encode_action(ACTION_STILL_EXISTS, incident_id, record.verification_cycle),
                "title": _option_label(VERIFICATION_STILL_EXISTS, lang),
            },
            {
                "id": encode_action(ACTION_UNSURE, incident_id, record.verification_cycle),
                "title": _option_label(VERIFICATION_UNSURE, lang),
            },
        ]
        try:
            if self._is_telegram_worker(record.worker_phone):
                await self._telegram_transport().send_verification_prompt(record.worker_phone, body, buttons)
            elif self.whatsapp.interactive_actions_supported:
                await self.whatsapp.send_verification_prompt(record.worker_phone, body, buttons)
            else:
                fallback = body + "\n\n" + (CLARIFICATION_PROMPT.get(lang) or CLARIFICATION_PROMPT["en"])
                await self.whatsapp.send_worker_text(record.worker_phone, fallback)
        except (WhatsAppSendError, TelegramSendError):
            log.warning("worker_verification_delivery_failed incident=%s", incident_id)
            return FollowupResult(
                incident_id=incident_id,
                status=record.status,
                verification_status=VERIFICATION_PENDING,
                verification_cycle=record.verification_cycle,
                worker_language=record.worker_language,
                worker_notified=False,
                error=ERROR_DELIVERY,
            )
        self._mark_event(record, event_id)
        try:
            self._persist(
                record,
                event_type="worker_verification_requested",
                previous_status=incoming_status,
                actor=actor,
                source="slack",
                timestamps={"resolved_at": _now()},
            )
        except Exception:
            log.exception("repository_update_failed during verification request")
        log.info("worker_verification_message_sent incident=%s", incident_id)
        return FollowupResult(
            incident_id=incident_id,
            previous_status=incoming_status,
            status=record.status,
            verification_status=VERIFICATION_PENDING,
            verification_cycle=record.verification_cycle,
            worker_language=record.worker_language,
            worker_notified=True,
        )

    async def handle_worker_verification_response(
        self,
        *,
        text: str | None = None,
        action_id: str | None = None,
        worker_phone: str | None = None,
        incident_id: str | None = None,
        event_id: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> FollowupResult:
        parsed_action = parse_action_id(action_id)
        if message:
            interactive = extract_interactive_reply(message)
            if interactive:
                parsed_action = parse_action_id(interactive.get("action")) or parsed_action
                text = text or interactive.get("title")
                incident_id = incident_id or interactive.get("incident_id")
        cycle = None
        choice = None
        if parsed_action:
            incident_id = incident_id or parsed_action.get("incident_id")
            if parsed_action.get("cycle"):
                try:
                    cycle = int(parsed_action["cycle"])
                except (TypeError, ValueError):
                    cycle = None
            choice = {
                ACTION_YES: VERIFICATION_CONFIRMED,
                ACTION_STILL_EXISTS: VERIFICATION_STILL_EXISTS,
                ACTION_UNSURE: VERIFICATION_UNSURE,
            }.get(parsed_action.get("action") or "")
        record = self.store.get(incident_id) if incident_id else None
        if record is None and worker_phone:
            pending = self.store.pending_for_worker(worker_phone)
            if len(pending) == 1:
                record = pending[0]
            elif len(pending) > 1:
                return FollowupResult(error=ERROR_AMBIGUOUS, worker_reply="Please reply using the incident buttons.")
        if record is None:
            return FollowupResult(incident_id=incident_id, error=ERROR_STALE)
        record = self._reload_status(record)
        if self._event_seen(record, event_id):
            return FollowupResult(
                incident_id=record.incident_id,
                status=record.status,
                verification_status=record.verification_status,
                error=ERROR_DUPLICATE,
            )
        if choice is None:
            choice = parse_verification_response(text, record.worker_language)
        if choice is None:
            log.info("worker_verification_ambiguous incident=%s", record.incident_id)
            lang = _language(record.worker_language)
            if record.worker_phone:
                prompt = CLARIFICATION_PROMPT.get(lang) or CLARIFICATION_PROMPT["en"]
                try:
                    if self._is_telegram_worker(record.worker_phone):
                        await self._telegram_transport().send_worker_text(record.worker_phone, prompt)
                    else:
                        await self.whatsapp.send_worker_text(record.worker_phone, prompt)
                except (WhatsAppSendError, TelegramSendError):
                    pass
            return FollowupResult(
                incident_id=record.incident_id,
                status=record.status,
                verification_status=record.verification_status,
                verification_cycle=record.verification_cycle,
                error=ERROR_AMBIGUOUS,
                worker_reply=CLARIFICATION_PROMPT.get(lang),
            )
        stale = validate_verification_context(record, cycle=cycle)
        if stale:
            log.info("stale_verification_response_ignored incident=%s", record.incident_id)
            return FollowupResult(
                incident_id=record.incident_id,
                status=record.status,
                verification_status=record.verification_status,
                error=stale,
            )
        if choice == VERIFICATION_CONFIRMED:
            result = await self.confirm_safe_and_close(record.incident_id, actor=worker_phone)
        elif choice == VERIFICATION_STILL_EXISTS:
            result = await self.reopen_incident(record.incident_id, actor=worker_phone)
        else:
            result = await self.handle_unsure_response(record.incident_id, actor=worker_phone)
        if result.error != ERROR_REPO:
            self._mark_event(record, event_id)
        return result

    async def confirm_safe_and_close(
        self,
        incident_id: str,
        *,
        actor: str | None = None,
        source: str = "whatsapp",
        slack_closure: dict[str, Any] | None = None,
    ) -> FollowupResult:
        record = self._reload_status(self._record(incident_id))
        previous = record.status
        outcome = validate_status_transition(previous, STATUS_CLOSED)
        result = FollowupResult(
            incident_id=incident_id,
            previous_status=previous,
            status=record.status,
            verification_cycle=record.verification_cycle,
            worker_language=record.worker_language,
        )
        if outcome == "invalid":
            result.error = ERROR_TRANSITION
            return result
        risk_level = self._closure_risk_level(record)
        from guardrails.output_validation import validate_closure_request

        if slack_closure:
            record.slack_closed_action = slack_closure
            record.reviewed_by_human = True
        closure = validate_closure_request(
            risk_level=risk_level,
            source=source,
            reviewed_by_human=record.reviewed_by_human,
            slack_closed_action=record.slack_closed_action or slack_closure,
            incident_id=incident_id,
        )
        if not closure.get("approved"):
            result.error = ERROR_HUMAN_REVIEW
            result.worker_reply = "A safety officer must confirm closure in Slack for High and Critical incidents."
            try:
                self._persist(
                    record,
                    event_type="closure_blocked",
                    previous_status=previous,
                    actor=actor,
                    source=source,
                    extra={
                        "event": "guardrail_closure_blocked",
                        "risk_level": risk_level,
                        "reason": "human_review_required",
                    },
                )
            except Exception:
                log.exception("repository_update_failed during closure block")
            await self._notify_slack(
                record,
                "Human approval required according to SPEC.md\n"
                f"Worker confirmed the area is safe, but {risk_level or 'this'} risk "
                "cannot auto-close. An authorized officer must press Closed in this thread.",
            )
            log.info("closure_blocked_human_review incident=%s risk=%s", incident_id, risk_level)
            return result
        closed_at = _now()
        record.status = STATUS_CLOSED
        record.verification_status = VERIFICATION_CONFIRMED
        evidence = dict(slack_closure or record.slack_closed_action or {})
        extra = {"event": "worker_confirmed_safe"}
        if evidence:
            extra.update(
                {
                    "closed_by": evidence.get("closed_by") or actor,
                    "closed_source": evidence.get("source") or source,
                    "closed_timestamp": evidence.get("timestamp") or closed_at,
                    "slack_action_id": evidence.get("slack_action_id") or evidence.get("action_id"),
                    "action": evidence.get("action") or "Closed",
                }
            )
        try:
            self._persist(
                record,
                event_type="incident_closed",
                previous_status=previous,
                actor=actor,
                source=source,
                extra=extra,
                timestamps={"closed_at": closed_at},
            )
        except Exception:
            record.status = previous
            record.verification_status = VERIFICATION_PENDING
            log.exception("repository_update_failed during close")
            result.error = ERROR_REPO
            result.worker_reply = "Unable to update the incident record. Please retry."
            return result
        self.store.put(record)
        await self._notify_slack(record, "Worker confirmed the area is safe.\n\nIncident status: Closed.")
        log.info("incident_closed_after_verification incident=%s", incident_id)
        result.status = STATUS_CLOSED
        result.verification_status = VERIFICATION_CONFIRMED
        result.closed = True
        result.resolution_timestamp = closed_at
        result.after_evidence_added = bool(record.processed_file_ids)
        return result

    def _closure_risk_level(self, record: FollowupRecord) -> str | None:
        if record.risk_level:
            return record.risk_level
        if self.repository is None or not record.uuid:
            return record.risk_level
        try:
            row = self.repository.get_incident(UUID(record.uuid))
        except Exception:
            return record.risk_level
        if row is None:
            return record.risk_level
        if isinstance(row, dict):
            return row.get("current_risk_level") or row.get("risk_level") or record.risk_level
        return getattr(row, "current_risk_level", None) or getattr(row, "risk_level", None) or record.risk_level

    async def reopen_incident(self, incident_id: str, *, actor: str | None = None) -> FollowupResult:
        record = self._reload_status(self._record(incident_id))
        previous = record.status
        outcome = validate_status_transition(previous, STATUS_IN_PROGRESS)
        result = FollowupResult(
            incident_id=incident_id,
            previous_status=previous,
            status=record.status,
            verification_cycle=record.verification_cycle,
            worker_language=record.worker_language,
            requires_risk_reassessment=True,
        )
        if outcome == "invalid":
            result.error = ERROR_TRANSITION
            return result
        record.status = STATUS_IN_PROGRESS
        record.verification_status = VERIFICATION_STILL_EXISTS
        record.reopen_count += 1
        try:
            self._persist(
                record,
                event_type="incident_reopened",
                previous_status=previous,
                actor=actor,
                source="whatsapp",
                extra={
                    "event": "worker_reports_still_exists",
                    "reopened": True,
                    "reopen_count": record.reopen_count,
                    "reopen_reason": "worker_reports_hazard_still_exists",
                },
            )
        except Exception:
            record.status = previous
            record.verification_status = VERIFICATION_PENDING
            record.reopen_count = max(record.reopen_count - 1, 0)
            log.exception("repository_update_failed during reopen")
            result.error = ERROR_REPO
            result.worker_reply = "Unable to update the incident record. Please retry."
            return result
        self.store.put(record)
        result.status = STATUS_IN_PROGRESS
        result.verification_status = VERIFICATION_STILL_EXISTS
        result.reopened = True
        notified = await self._renotify_team(record)
        result.team_renotified = notified
        if not notified:
            result.error = ERROR_TEAM_NOTIFY
        log.info("incident_reopened_after_verification incident=%s", incident_id)
        return result

    async def handle_unsure_response(self, incident_id: str, *, actor: str | None = None) -> FollowupResult:
        record = self._reload_status(self._record(incident_id))
        previous = record.status
        record.verification_status = VERIFICATION_UNSURE
        try:
            self._persist(
                record,
                event_type="worker_unsure",
                previous_status=previous,
                actor=actor,
                source="whatsapp",
            )
        except Exception:
            log.exception("repository_update_failed during unsure")
            return FollowupResult(
                incident_id=incident_id,
                previous_status=previous,
                status=record.status,
                error=ERROR_REPO,
            )
        self.store.put(record)
        await self._notify_slack(
            record,
            "Worker could not confirm that the area is safe.\nVerification remains pending.",
        )
        log.info("worker_verification_unsure incident=%s", incident_id)
        return FollowupResult(
            incident_id=incident_id,
            previous_status=previous,
            status=record.status,
            verification_status=VERIFICATION_UNSURE,
            verification_cycle=record.verification_cycle,
            worker_language=record.worker_language,
        )

    async def handle_after_photo(
        self,
        *,
        incident_id: str,
        content: bytes,
        filename: str | None = None,
        content_type: str | None = None,
        slack_file_id: str | None = None,
        thread_ts: str | None = None,
        channel_id: str | None = None,
        actor: str | None = None,
        event_id: str | None = None,
    ) -> FollowupResult:
        record = self._record(incident_id)
        if thread_ts and record.slack_thread_ts and thread_ts != record.slack_thread_ts:
            return FollowupResult(incident_id=incident_id, error=ERROR_WRONG_THREAD)
        if channel_id and record.slack_channel_id and channel_id != record.slack_channel_id:
            return FollowupResult(incident_id=incident_id, error=ERROR_WRONG_THREAD)
        mime = (content_type or "").split(";")[0].strip().lower()
        if mime and mime not in IMAGE_CONTENT_TYPES and not mime.startswith("image/"):
            return FollowupResult(incident_id=incident_id, error=ERROR_UNSUPPORTED_FILE)
        file_key = slack_file_id or event_id
        if file_key and file_key in record.processed_file_ids:
            return FollowupResult(
                incident_id=incident_id,
                after_evidence_added=True,
                error=ERROR_DUPLICATE,
                status=record.status,
            )
        if self.repository is None or not record.uuid:
            if file_key:
                record.processed_file_ids.append(file_key)
            self.store.put(record)
            return FollowupResult(incident_id=incident_id, after_evidence_added=True, status=record.status)
        from database.schemas import EvidenceCreate, EvidenceFile, IncidentUpdateCreate

        try:
            self.repository.add_evidence(
                EvidenceFile(content=content, filename=filename, content_type=content_type or "image/jpeg"),
                UUID(record.uuid),
                "verification",
                metadata=EvidenceCreate(
                    evidence_type="after",
                    source="slack",
                    uploaded_by=actor,
                    external_message_id=slack_file_id,
                ),
                filename=filename,
                content_type=content_type or "image/jpeg",
            )
            self.repository.add_update(
                IncidentUpdateCreate(
                    incident_id=UUID(record.uuid),
                    update_type="after_evidence_added",
                    actor_type="safety_officer",
                    actor_reference=actor,
                    metadata={"source": "slack", "file_id": slack_file_id},
                )
            )
        except Exception:
            log.exception("after_evidence_add_failed")
            return FollowupResult(incident_id=incident_id, error=ERROR_EVIDENCE, status=record.status)
        if file_key:
            record.processed_file_ids.append(file_key)
        self.store.put(record)
        log.info("after_evidence_added incident=%s", incident_id)
        return FollowupResult(incident_id=incident_id, after_evidence_added=True, status=record.status)

    async def handle_slack_file_event(self, event: dict[str, Any]) -> FollowupResult | None:
        extracted = extract_slack_file(event)
        if extracted is None:
            return None
        thread_ts = extracted.get("thread_ts")
        record = next(
            (r for r in self.store.records.values() if r.slack_thread_ts and r.slack_thread_ts == thread_ts),
            None,
        )
        if record is None:
            return FollowupResult(error=ERROR_WRONG_THREAD)
        mime = str(extracted.get("mimetype") or "")
        if (
            mime
            and mime not in IMAGE_CONTENT_TYPES
            and not str(mime).startswith("image/")
            and mime
            not in {
                "jpg",
                "jpeg",
                "png",
                "webp",
                "gif",
            }
        ):
            return FollowupResult(incident_id=record.incident_id, error=ERROR_UNSUPPORTED_FILE)
        content = event.get("file_bytes") or b"after-photo"
        if not isinstance(content, (bytes, bytearray)):
            content = b"after-photo"
        return await self.handle_after_photo(
            incident_id=record.incident_id,
            content=bytes(content),
            filename=extracted.get("name"),
            content_type=mime if str(mime).startswith("image/") else "image/jpeg",
            slack_file_id=extracted.get("id"),
            thread_ts=thread_ts,
            channel_id=extracted.get("channel"),
            actor=extracted.get("user"),
            event_id=extracted.get("event_id"),
        )

    async def _notify_slack(self, record: FollowupRecord, text: str) -> bool:
        if not record.slack_channel_id or not record.slack_thread_ts:
            return False
        try:
            await self.slack.post_thread_reply(
                channel=record.slack_channel_id, thread_ts=record.slack_thread_ts, text=text
            )
            return True
        except SlackPostError:
            log.warning("slack presentation update failed after repository success")
            return False

    async def _renotify_team(self, record: FollowupRecord) -> bool:
        extra = ""
        if record.reopen_count > 1:
            extra = f"\nThis incident has failed worker verification {record.reopen_count} times."
        text = (
            "⚠️ Worker verification failed.\n\n"
            "The reporting worker says the hazard still exists.\n\n"
            f"Incident: {record.incident_id}\n"
            f"Status: {STATUS_IN_PROGRESS}\n"
            f"Location: {record.location or 'Unknown'}\n"
            f"Assigned team: {record.assigned_team or 'Unknown'}\n\n"
            "Please re-check the area."
            f"{extra}"
        )
        sent = await self._notify_slack(record, text)
        if sent:
            log.info("team_renotified incident=%s team=%s", record.incident_id, record.assigned_team)
        else:
            log.warning("team_renotification_failed incident=%s", record.incident_id)
        return sent


_default_service: FollowupService | None = None


def get_followup_service() -> FollowupService:
    global _default_service
    if _default_service is None:
        _default_service = FollowupService()
    return _default_service


async def start_worker_verification(
    incident: Any, *, service: FollowupService | None = None, **kwargs: Any
) -> FollowupResult:
    return await (service or get_followup_service()).start_worker_verification(incident, **kwargs)


async def handle_worker_verification_response(
    *, service: FollowupService | None = None, **kwargs: Any
) -> FollowupResult:
    return await (service or get_followup_service()).handle_worker_verification_response(**kwargs)


async def start_worker_verification_alert(incident_json: str) -> str:
    """Ask the original worker to confirm the area is safe after Slack Resolved."""
    from agentkernel.core import ToolContext

    ctx = ToolContext.get()
    session = ctx.session
    cache = session.get_non_volatile_cache()
    draft: dict[str, Any] = {}
    for key in ("incident_draft", "last_coordination_result", "pending_worker_verification"):
        cached = cache.get(key) if hasattr(cache, "get") else None
        if isinstance(cached, dict):
            draft.update(cached)
    if incident_json and str(incident_json).strip():
        try:
            parsed = json.loads(incident_json)
            if isinstance(parsed, dict):
                draft.update(parsed)
        except json.JSONDecodeError:
            pass
    result = await start_worker_verification(draft)
    cache.set("pending_worker_verification", json.loads(result.model_dump_json()))
    cache.set("workflow_stage", "worker_verification")
    return result.model_dump_json()


async def handle_worker_verification_reply(reply_json: str) -> str:
    """Apply a worker Yes / No / Not sure verification reply."""
    from agentkernel.core import ToolContext

    ctx = ToolContext.get()
    session = ctx.session
    cache = session.get_non_volatile_cache()
    payload: dict[str, Any] = {}
    pending = cache.get("pending_worker_verification") if hasattr(cache, "get") else None
    if isinstance(pending, dict):
        payload["incident_id"] = pending.get("incident_id")
    if reply_json and str(reply_json).strip():
        try:
            parsed = json.loads(reply_json)
            if isinstance(parsed, dict):
                payload.update(parsed)
            else:
                payload["text"] = str(reply_json)
        except json.JSONDecodeError:
            payload["text"] = str(reply_json)
    if not payload.get("incident_id") and not payload.get("worker_phone"):
        return FollowupResult(error=ERROR_STALE).model_dump_json()
    result = await handle_worker_verification_response(
        text=payload.get("text") or payload.get("body"),
        action_id=payload.get("action_id") or payload.get("id"),
        worker_phone=payload.get("worker_phone") or payload.get("from"),
        incident_id=payload.get("incident_id"),
        event_id=payload.get("event_id") or payload.get("message_id"),
        message=payload.get("message") if isinstance(payload.get("message"), dict) else payload,
    )
    cache.set("last_followup_result", json.loads(result.model_dump_json()))
    return result.model_dump_json()


def create_followup_agent(*, model: Any = None, handoffs: list[Any] | None = None) -> Any:
    from agentkernel.openai import OpenAIToolBuilder

    from ak_bootstrap import pin_openai_agents_sdk

    pin_openai_agents_sdk()
    from agents import Agent  # type: ignore[attr-defined]

    tools = OpenAIToolBuilder.bind([start_worker_verification_alert, handle_worker_verification_reply])
    kwargs: dict[str, Any] = {}
    if model is not None:
        kwargs["model"] = model
    if handoffs:
        kwargs["handoffs"] = handoffs
    return Agent(
        name="followup_agent",
        handoff_description="Verifies remediation with the original worker and closes or reopens the same incident.",
        instructions=(
            "You are followup_agent. After Slack Resolved, call start_worker_verification_alert. "
            "When the worker replies, call handle_worker_verification_reply. "
            "Yes closes the incident. No, still exists reopens to In Progress. Not sure stays pending. "
            "Do not close from arbitrary Yes text without an active verification. "
            "Do not recompute risk or invent safety procedures."
        ),
        tools=tools,
        **kwargs,
    )


# Re-export for tests and callers that import lifecycle names from this module.
STATUS_NEW = LIFECYCLE[0]
validate_followup_transition = validate_status_transition
can_followup_transition = can_transition
