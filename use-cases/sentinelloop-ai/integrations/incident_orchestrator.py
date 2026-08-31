"""End-to-end WhatsApp incident orchestration.

Wires intake → duplicate_tools → incident → risk → guidance → WhatsApp →
coordination → repository. Does not re-implement agent logic.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from database.schemas import EvidenceCreate, EvidenceFile, IncidentCreate, IncidentUpdateCreate
from integrations.whatsapp import WhatsAppSendError, parse_action_id
from integrations.whatsapp_handler import (
    UNSUPPORTED_WORKER_REPLY,
    NormalizedWhatsAppMessage,
    WhatsAppCloudTransport,
)
from tools.duplicate_tools import DuplicateResult, check_for_duplicate
from tools.idempotency import EventIdempotencyStore, event_key
from tools.lifecycle import (
    STATUS_ASSESSED,
    STATUS_ASSIGNED,
    STATUS_IN_PROGRESS,
    STATUS_NEW,
    STATUS_VALIDATING,
    to_display_status,
    to_repository_status,
)

log = logging.getLogger("sentinelloop.orchestrator")

NV_PENDING = "pending_clarification"
NV_PENDING_FIELD = "pending_clarification_field"
NV_CLARIFICATION_MSG = "clarification_message_id"
NV_CANONICAL = "current_incident_id"
NV_CANONICAL_UUID = "current_incident_uuid"
NV_DRAFT = "incident_draft"
NV_DUPLICATE = "duplicate_context"
NV_PENDING_MEDIA = "pending_media"
NV_CLARIFICATION_INDEX = "clarification_message_index"
NV_LANGUAGE = "detected_language"
NV_STAGE = "workflow_stage"
NV_ORCH_RESULT = "last_orchestration_result"
NV_VERIFICATION = "pending_worker_verification"
NV_LAST_RESULT = "last_intake_result"

NON_HAZARD_REPLY = (
    "Thanks — I can help with workplace hazard reports. "
    "If you see a safety issue, send a short description or a photo."
)
ACK_LINE = "Your safety report has been recorded."
AMBIGUOUS_REPLY = "Please reply to the question I sent so I can attach this to the right report."
STALE_REPLY = "That question is no longer open. If the hazard is still there, please send a new report."
IMAGE_ONLY_CLARIFICATION = "Please describe the hazard you photographed."

ACTION_YES = "verification_yes"
ACTION_STILL_EXISTS = "verification_still_exists"
ACTION_UNSURE = "verification_unsure"


def _redact_phone(phone: str) -> str:
    text = (phone or "").strip()
    if len(text) <= 4:
        return "****"
    return f"{text[:3]}******{text[-3:]}"


def _load_agent_fn(filename: str, attr: str) -> Any:
    path = Path(__file__).resolve().parent.parent / "agents" / filename
    spec = importlib.util.spec_from_file_location(f"sentinelloop_orch_{filename}_{attr}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}:{attr}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, attr)


def _as_dict(value: Any) -> dict[str, Any]:
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


def _cache(session: Any) -> Any:
    if session is None:
        return None
    getter = getattr(session, "get_non_volatile_cache", None)
    return getter() if callable(getter) else None


def _cache_get(session: Any, key: str, default: Any = None) -> Any:
    cache = _cache(session)
    if cache is None:
        return default
    value = cache.get(key) if hasattr(cache, "get") else None
    return default if value is None else value


def _cache_set(session: Any, key: str, value: Any) -> None:
    cache = _cache(session)
    if cache is None:
        return
    cache.set(key, value)


def _store_session(store: Any, session: Any) -> None:
    if store is not None and session is not None and hasattr(store, "store"):
        store.store(session)


class OrchestrationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider_message_id: str
    session_id: str | None = None
    incident_id: str | None = None
    is_hazard_report: bool = False
    duplicate_detected: bool = False
    canonical_incident_id: str | None = None
    clarification_required: bool = False
    clarification_sent: bool = False
    risk_completed: bool = False
    guidance_generated: bool = False
    guidance_sent: bool = False
    coordination_completed: bool = False
    evidence_attached: bool = False
    status: str | None = None
    error: str | None = None
    idempotent_replay: bool = False
    unsupported: bool = False


class IncidentOrchestrator:
    def __init__(
        self,
        *,
        repository: Any | None = None,
        whatsapp: WhatsAppCloudTransport | None = None,
        coordination: Any | None = None,
        followup: Any | None = None,
        intake_fn: Any | None = None,
        duplicate_fn: Any | None = None,
        incident_fn: Any | None = None,
        risk_fn: Any | None = None,
        guidance_fn: Any | None = None,
        session_store: Any | None = None,
        idempotency: EventIdempotencyStore | None = None,
    ) -> None:
        self.repository = repository
        self.whatsapp = whatsapp or WhatsAppCloudTransport()
        self.coordination = coordination
        self.followup = followup
        self.intake_fn = intake_fn
        self.duplicate_fn = duplicate_fn or check_for_duplicate
        self.incident_fn = incident_fn
        self.risk_fn = risk_fn
        self.guidance_fn = guidance_fn
        self.session_store = session_store
        self.idempotency = idempotency or EventIdempotencyStore()
        self.pipeline_trace: list[str] = []
        self._pending_media: dict[str, dict[str, Any]] = {}
        self._processed_evidence: set[str] = set()
        self._ref_seq = 0
        self._stats: dict[str, int] = {
            "incoming_whatsapp_reports": 0,
            "hazard_reports": 0,
            "non_hazard_messages": 0,
            "image_reports": 0,
            "duplicates": 0,
            "clarifications": 0,
            "guidance_delivery_success": 0,
            "guidance_delivery_failure": 0,
            "slack_coordination_success": 0,
            "slack_coordination_failure": 0,
            "end_to_end_success": 0,
            "webhook_duplicates": 0,
        }

    def _note(self, key: str) -> None:
        self._stats[key] = self._stats.get(key, 0) + 1

    def _trace(self, step: str) -> None:
        self.pipeline_trace.append(step)

    def _intake(self) -> Any:
        if self.intake_fn is None:
            self.intake_fn = _load_agent_fn("intake_agent.py", "process_intake")
        return self.intake_fn

    def _incident(self) -> Any:
        if self.incident_fn is None:
            self.incident_fn = _load_agent_fn("incident_agent.py", "analyze_incident")
        return self.incident_fn

    def _risk(self) -> Any:
        if self.risk_fn is None:
            self.risk_fn = _load_agent_fn("risk_agent.py", "assess_risk")
        return self.risk_fn

    def _guidance(self) -> Any:
        if self.guidance_fn is None:
            self.guidance_fn = _load_agent_fn("guidance_agent.py", "generate_guidance")
        return self.guidance_fn

    def _coordination_call(self) -> Any:
        if self.coordination is not None:
            coord = getattr(self.coordination, "coordinate_incident", self.coordination)
            return coord
        return _load_agent_fn("coordination_agent.py", "coordinate_incident")

    def _next_ref(self) -> str:
        self._ref_seq += 1
        return f"INC-{self._ref_seq:04d}"

    def _load_session(self, sender_id: str, session: Any | None = None) -> tuple[Any, Any]:
        if session is not None:
            return session, self.session_store
        store = self.session_store
        if store is None:
            try:
                from agentkernel.core.runtime import Runtime

                store = Runtime.current().sessions()
            except Exception:
                from agentkernel.core.session.in_memory import InMemorySessionStore

                store = InMemorySessionStore()
                self.session_store = store
        loaded = store.load(sender_id)
        return loaded, store

    def _result(self, message: NormalizedWhatsAppMessage, **kwargs: Any) -> OrchestrationResult:
        return OrchestrationResult(provider_message_id=message.provider_message_id, **kwargs)

    async def process_incoming_whatsapp_message(
        self,
        message: NormalizedWhatsAppMessage | dict[str, Any],
        *,
        session: Any | None = None,
    ) -> OrchestrationResult:
        if isinstance(message, dict):
            message = NormalizedWhatsAppMessage.model_validate(message)
        self.pipeline_trace = []
        self._note("incoming_whatsapp_reports")
        key = event_key("whatsapp", message.provider_message_id)
        cached = self.idempotency.get(key)
        if cached is not None:
            self._note("webhook_duplicates")
            log.info("whatsapp_duplicate_event_ignored")
            replay = OrchestrationResult.model_validate(cached)
            replay.idempotent_replay = True
            return replay
        if not self.idempotency.begin(key):
            self._note("webhook_duplicates")
            log.info("whatsapp_duplicate_event_ignored")
            again = self.idempotency.get(key)
            if again is not None:
                replay = OrchestrationResult.model_validate(again)
                replay.idempotent_replay = True
                return replay
            return self._result(message, error="duplicate_in_flight", idempotent_replay=True)

        try:
            result = await self._dispatch(message, session=session)
        except Exception as exc:
            log.exception("orchestration_failed")
            result = self._result(message, error=str(exc) or "orchestration_failed")
            self.idempotency.abandon(key)
            return result

        stored = self.idempotency.complete(key, result.model_dump(mode="json"))
        out = OrchestrationResult.model_validate(stored)
        log.info(
            "orchestration_completed hazard=%s incident=%s error=%s",
            out.is_hazard_report,
            out.canonical_incident_id,
            out.error,
        )
        return out

    async def _dispatch(self, message: NormalizedWhatsAppMessage, *, session: Any | None) -> OrchestrationResult:
        ak_session, store = self._load_session(message.sender_id, session=session)
        session_id = getattr(ak_session, "id", message.sender_id)

        if message.interactive_action_id:
            parsed = parse_action_id(message.interactive_action_id)
            if parsed and parsed.get("action") in {ACTION_YES, ACTION_STILL_EXISTS, ACTION_UNSURE}:
                return await self._handle_verification(message, ak_session, store, parsed)

        pending = bool(_cache_get(ak_session, NV_PENDING))
        index = dict(_cache_get(ak_session, NV_CLARIFICATION_INDEX) or {})
        reply_id = message.reply_to_message_id
        if (
            reply_id
            and isinstance(index.get(str(reply_id)), dict)
            and index[str(reply_id)].get("status") == "completed"
        ):
            log.info("stale_clarification_ignored")
            try:
                await self.whatsapp.send_text_message(message.sender_id, STALE_REPLY)
            except WhatsAppSendError:
                pass
            return self._result(
                message,
                session_id=session_id,
                incident_id=_cache_get(ak_session, NV_CANONICAL),
                error="stale_clarification",
            )
        if not message.supported:
            if pending:
                try:
                    await self.whatsapp.send_text_message(message.sender_id, UNSUPPORTED_WORKER_REPLY)
                except WhatsAppSendError:
                    log.warning("whatsapp_unsupported_ack_failed")
                return self._result(
                    message,
                    session_id=session_id,
                    clarification_required=True,
                    unsupported=True,
                    incident_id=_cache_get(ak_session, NV_CANONICAL),
                )
            return self._result(message, session_id=session_id, unsupported=True)

        if pending:
            return await self.process_clarification_reply(message, session=ak_session, store=store)

        if message.message_type == "image" and not (message.text or message.caption):
            if _cache_get(ak_session, NV_CANONICAL) or _cache_get(ak_session, NV_DRAFT):
                return await self._attach_followup_media(message, ak_session, store)

        return await self.process_new_report(message, session=ak_session, store=store)

    async def _handle_verification(
        self,
        message: NormalizedWhatsAppMessage,
        session: Any,
        store: Any,
        parsed: dict[str, str],
    ) -> OrchestrationResult:
        handler = self.followup
        if handler is None:
            try:
                handler = _load_agent_fn("followup_agent.py", "handle_worker_verification_response")
            except Exception:
                handler = None
        if handler is None:
            return self._result(message, session_id=getattr(session, "id", None), error="followup_unavailable")
        call = (
            handler.handle_worker_verification_response
            if hasattr(handler, "handle_worker_verification_response")
            else handler
        )
        await call(
            text=message.interactive_title or message.text,
            action_id=message.interactive_action_id,
            incident_id=parsed.get("incident_id"),
            event_id=message.provider_message_id,
            worker_phone=message.sender_id,
        )
        _store_session(store, session)
        return self._result(
            message,
            session_id=getattr(session, "id", None),
            incident_id=parsed.get("incident_id"),
            canonical_incident_id=parsed.get("incident_id"),
        )

    async def process_new_report(
        self,
        message: NormalizedWhatsAppMessage,
        *,
        session: Any,
        store: Any,
    ) -> OrchestrationResult:
        self._retain_media(message)
        intake = await self._run_intake(message, session, store)
        self._trace("intake_agent")
        log.info("intake_completed hazard=%s", getattr(intake, "is_hazard_report", None))
        intake_data = _as_dict(intake)
        is_hazard = bool(intake_data.get("is_hazard_report"))
        if message.media and not (message.text or message.caption):
            is_hazard = True
            intake_data["is_hazard_report"] = True
            intake_data["has_image"] = True
        if not is_hazard:
            self._note("non_hazard_messages")
            return await self._handle_non_hazard(message, session, store, intake_data)

        self._note("hazard_reports")
        if message.media:
            self._note("image_reports")
        duplicate = await self.resolve_duplicate(intake_data, message=message)
        self._trace("duplicate_tools")
        if duplicate.status == "confirmed" and duplicate.action in {"reuse", "reopen"}:
            log.info("incident_duplicate_found incident=%s", duplicate.canonical_incident_id)
            self._note("duplicates")
        else:
            log.info("incident_new_candidate")

        _cache_set(session, NV_DUPLICATE, duplicate.model_dump(mode="json"))
        canonical = await self._apply_duplicate_identity(duplicate, intake_data, message, session)
        incident = await self._run_incident_agent(intake_data, session=session, canonical=canonical)
        self._trace("incident_agent")
        merged = {
            **intake_data,
            **_as_dict(incident),
            **canonical,
            "has_image": bool(message.media) or intake_data.get("has_image"),
        }
        if message.media:
            merged["has_image"] = True
        _cache_set(session, NV_DRAFT, _session_draft(merged))
        _cache_set(session, NV_LANGUAGE, merged.get("language") or _cache_get(session, NV_LANGUAGE))
        _store_session(store, session)

        needs = bool(merged.get("needs_clarification")) and not bool(merged.get("skip_clarification"))
        if needs:
            return await self._pause_for_clarification(message, session, store, merged)

        return await self.continue_after_incident_extraction(message, session, store, merged)

    async def process_clarification_reply(
        self,
        message: NormalizedWhatsAppMessage,
        *,
        session: Any,
        store: Any,
    ) -> OrchestrationResult:
        index = dict(_cache_get(session, NV_CLARIFICATION_INDEX) or {})
        reply_id = message.reply_to_message_id
        current_msg = _cache_get(session, NV_CLARIFICATION_MSG)
        if reply_id and reply_id in index:
            meta = index[reply_id]
            if isinstance(meta, dict) and meta.get("status") == "completed":
                log.info("stale_clarification_ignored")
                try:
                    await self.whatsapp.send_text_message(message.sender_id, STALE_REPLY)
                except WhatsAppSendError:
                    pass
                return self._result(
                    message,
                    session_id=getattr(session, "id", None),
                    incident_id=_cache_get(session, NV_CANONICAL),
                    error="stale_clarification",
                )
        elif reply_id and current_msg and reply_id != current_msg and reply_id not in index:
            pending_ids = [k for k, v in index.items() if isinstance(v, dict) and v.get("status") == "pending"]
            if len(pending_ids) > 1:
                try:
                    await self.whatsapp.send_text_message(message.sender_id, AMBIGUOUS_REPLY)
                except WhatsAppSendError:
                    pass
                return self._result(
                    message,
                    session_id=getattr(session, "id", None),
                    clarification_required=True,
                    error="ambiguous_draft",
                )

        self._retain_media(message)
        previous = _as_dict(_cache_get(session, NV_DRAFT))
        duplicate_ctx = _as_dict(_cache_get(session, NV_DUPLICATE))
        if not message.supported:
            try:
                await self.whatsapp.send_text_message(message.sender_id, UNSUPPORTED_WORKER_REPLY)
            except WhatsAppSendError:
                pass
            return self._result(
                message,
                session_id=getattr(session, "id", None),
                incident_id=previous.get("incident_id") or _cache_get(session, NV_CANONICAL),
                clarification_required=True,
                unsupported=True,
            )

        intake = await self._run_intake(message, session, store)
        self._trace("intake_agent")
        intake_data = _as_dict(intake)
        text = intake_data.get("translated_text") or intake_data.get("raw_text") or message.text or message.caption
        draft = dict(previous)
        for key, value in intake_data.items():
            if value is None or value == "" or value == []:
                continue
            if key in {"needs_clarification", "is_hazard_report"}:
                continue
            draft[key] = value
        if text:
            draft["clarification_answer"] = text
            draft["translated_text"] = intake_data.get("translated_text") or previous.get("translated_text") or text
            draft["raw_text"] = _join_text(previous.get("raw_text"), intake_data.get("raw_text") or text)
        if message.media:
            draft["has_image"] = True
        for key in ("qr_location", "qr_equipment", "language", "session_id", "source", "location_confidence", "clean_text"):
            if previous.get(key) and not draft.get(key):
                draft[key] = previous[key]
        log.info("clarification_reply_merged")
        incident = await self._incident()(
            draft,
            previous=previous or None,
            session=session,
            incident_id=draft.get("incident_id") or _cache_get(session, NV_CANONICAL),
        )
        self._trace("incident_agent")
        merged = {**draft, **_as_dict(incident)}
        if previous.get("hazard_category") and not merged.get("hazard_category"):
            merged["hazard_category"] = previous["hazard_category"]
        if previous.get("qr_location"):
            merged["qr_location"] = previous["qr_location"]
            merged["location"] = merged.get("location") or previous.get("location") or previous["qr_location"]
        if previous.get("qr_equipment"):
            merged["qr_equipment"] = previous["qr_equipment"]
            merged["equipment_involved"] = merged.get("equipment_involved") or previous.get("equipment_involved")
        if message.media:
            merged["has_image"] = True
        merged["incident_id"] = merged.get("incident_id") or _cache_get(session, NV_CANONICAL)
        if duplicate_ctx:
            merged["duplicate_count"] = duplicate_ctx.get("duplicate_count") or merged.get("duplicate_count")
            merged["canonical_incident_id"] = duplicate_ctx.get("canonical_incident_id") or merged.get("incident_id")
        _cache_set(session, NV_DRAFT, _session_draft(merged))
        _store_session(store, session)

        needs = bool(merged.get("needs_clarification")) and not bool(merged.get("skip_clarification"))
        if needs:
            return await self._pause_for_clarification(message, session, store, merged)

        _cache_set(session, NV_PENDING, False)
        _cache_set(session, NV_PENDING_FIELD, None)
        self._complete_clarification_index(session, current_msg)
        _store_session(store, session)
        return await self.continue_after_incident_extraction(message, session, store, merged)

    async def continue_after_incident_extraction(
        self,
        message: NormalizedWhatsAppMessage,
        session: Any,
        store: Any,
        merged: dict[str, Any],
    ) -> OrchestrationResult:
        persisted, persist_error = await self._ensure_canonical_incident(merged, message, session)
        merged.update(persisted)
        evidence_attached = await self.persist_initial_evidence(message, session, merged)
        if persist_error and not merged.get("incident_id"):
            return self._result(
                message,
                session_id=getattr(session, "id", None),
                is_hazard_report=True,
                evidence_attached=evidence_attached,
                error=persist_error,
            )
        return await self.run_risk_guidance_coordination(message, session, store, merged, evidence_attached)

    async def run_risk_guidance_coordination(
        self,
        message: NormalizedWhatsAppMessage,
        session: Any,
        store: Any,
        merged: dict[str, Any],
        evidence_attached: bool,
    ) -> OrchestrationResult:
        risk = None
        risk_error = None
        try:
            risk = await self._risk()(merged, session=session)
            self._trace("risk_agent")
            log.info("risk_completed")
            merged["risk"] = _as_dict(risk)
            merged["current_risk_level"] = merged["risk"].get("level")
            await self._transition(merged, STATUS_ASSESSED)
        except Exception as exc:
            log.warning("risk_agent_failed")
            risk_error = "risk_failed"
            merged["risk_error"] = str(exc) or risk_error

        guidance = None
        guidance_generated = False
        guidance_sent = False
        if risk is not None:
            try:
                payload = dict(merged)
                payload["language"] = merged.get("language") or _cache_get(session, NV_LANGUAGE)
                guidance = await self._guidance()(payload, session=session)
                self._trace("guidance_agent")
                log.info("guidance_generated")
                guidance_generated = True
                merged["guidance"] = _as_dict(guidance)
            except Exception:
                log.warning("guidance_generation_failed")

        if guidance is not None:
            worker_text = guidance.worker_text() if hasattr(guidance, "worker_text") else ""
            if worker_text:
                body = f"{worker_text}\n\n{ACK_LINE}"
                try:
                    await self.whatsapp.send_guidance(
                        message.sender_id,
                        body,
                        reply_to_message_id=message.provider_message_id,
                    )
                    self._trace("whatsapp_guidance")
                    log.info("guidance_sent")
                    guidance_sent = True
                    self._note("guidance_delivery_success")
                except WhatsAppSendError:
                    log.warning("guidance_send_failed")
                    self._note("guidance_delivery_failure")
                    await self._audit(merged, "guidance_send_failed", message="whatsapp delivery failed")

        coordination_completed = False
        if merged.get("incident_id") or merged.get("id"):
            log.info("slack_coordination_started")
            self._trace("coordination_agent")
            try:
                coord_payload = self.build_incident_record(merged)
                coordination = await self._coordination_call()(coord_payload)
                coord_data = _as_dict(coordination)
                merged["slack_metadata"] = {
                    "slack_channel_id": coord_data.get("slack_channel_id"),
                    "slack_message_ts": coord_data.get("slack_message_ts"),
                    "slack_thread_ts": coord_data.get("slack_thread_ts"),
                }
                merged["assigned_team"] = coord_data.get("assigned_team")
                posted = bool(coord_data.get("posted"))
                coordination_completed = posted
                if posted:
                    log.info("slack_coordination_completed")
                    self._note("slack_coordination_success")
                    await self._transition(merged, STATUS_ASSIGNED)
                    await self._audit(merged, "slack_coordination_completed")
                else:
                    log.warning("slack_coordination_failed")
                    self._note("slack_coordination_failure")
                    await self._audit(merged, "slack_coordination_failed", message=coord_data.get("coordination_error"))
            except Exception:
                log.warning("slack_coordination_failed")
                self._note("slack_coordination_failure")
                await self._audit(merged, "slack_coordination_failed")

        await self._enrich_repository(merged)
        _cache_set(session, NV_PENDING, False)
        _cache_set(session, NV_CANONICAL, merged.get("incident_id") or merged.get("incident_ref"))
        _cache_set(session, NV_STAGE, "assigned" if coordination_completed else _cache_get(session, NV_STAGE))
        _cache_set(session, NV_DRAFT, _session_draft(merged))
        result = self.build_orchestration_result(
            message,
            session=session,
            merged=merged,
            evidence_attached=evidence_attached,
            risk_completed=risk is not None,
            guidance_generated=guidance_generated,
            guidance_sent=guidance_sent,
            coordination_completed=coordination_completed,
            error=risk_error,
        )
        _cache_set(session, NV_ORCH_RESULT, result.model_dump(mode="json"))
        _store_session(store, session)
        if result.error is None and result.is_hazard_report and not result.clarification_required:
            if result.risk_completed:
                self._note("end_to_end_success")
        return result

    async def resolve_duplicate(
        self, intake_data: dict[str, Any], *, message: NormalizedWhatsAppMessage
    ) -> DuplicateResult:
        query = {
            "translated_text": intake_data.get("translated_text"),
            "raw_text": intake_data.get("raw_text"),
            "hazard_category": intake_data.get("hazard_category"),
            "location": intake_data.get("qr_location") or intake_data.get("location"),
            "qr_location": intake_data.get("qr_location"),
            "qr_equipment": intake_data.get("qr_equipment"),
            "worker_id": message.sender_id,
            "reporter_id": message.sender_id,
            "timestamp": message.received_at,
            "has_image": bool(message.media),
        }
        if self.repository is None:
            return DuplicateResult(status="none", action="create_new", reason="no_repository")
        return self.duplicate_fn(query, repository=self.repository)

    async def persist_initial_evidence(
        self,
        message: NormalizedWhatsAppMessage,
        session: Any,
        merged: dict[str, Any],
    ) -> bool:
        ident = merged.get("id") or merged.get("uuid")
        uuid = _as_uuid(ident)
        if uuid is None:
            refs = list(_cache_get(session, NV_PENDING_MEDIA) or [])
            if message.provider_message_id not in refs and message.media:
                refs.append(message.provider_message_id)
                _cache_set(session, NV_PENDING_MEDIA, refs)
            return False
        attached = False
        pending = list(_cache_get(session, NV_PENDING_MEDIA) or [])
        if message.provider_message_id not in pending and message.media:
            pending.append(message.provider_message_id)
        remaining: list[str] = []
        for mid in pending:
            blob = self._pending_media.get(mid)
            if not blob:
                remaining.append(mid)
                continue
            if await self._add_evidence(uuid, blob, merged):
                attached = True
            else:
                remaining.append(mid)
        _cache_set(session, NV_PENDING_MEDIA, remaining)
        return attached

    async def _add_evidence(self, incident_uuid: UUID, blob: dict[str, Any], merged: dict[str, Any]) -> bool:
        mid = str(blob.get("provider_message_id") or "")
        if not mid or mid in self._processed_evidence:
            return mid in self._processed_evidence
        content = blob.get("content")
        if not content:
            return False
        if self.repository is None or not hasattr(self.repository, "add_evidence"):
            self._processed_evidence.add(mid)
            return True
        mime = blob.get("mime_type") or "image/jpeg"
        try:
            self.repository.add_evidence(
                EvidenceFile(content=content, filename=None, content_type=mime),
                incident_uuid,
                "report",
                metadata=EvidenceCreate(
                    evidence_type="before",
                    source="whatsapp",
                    caption_or_description=blob.get("caption") or merged.get("translated_text"),
                    external_message_id=mid,
                ),
                content_type=mime,
            )
            self._processed_evidence.add(mid)
            log.info("whatsapp_evidence_added")
            await self._audit(merged, "evidence_added", metadata={"provider_message_id": mid})
            return True
        except Exception:
            log.warning("whatsapp_evidence_add_failed")
            return False

    def _retain_media(self, message: NormalizedWhatsAppMessage) -> None:
        if not message.media:
            return
        content = message.media.content
        if not content:
            self._pending_media.setdefault(
                message.provider_message_id,
                {
                    "provider_message_id": message.provider_message_id,
                    "media_id": message.media.media_id,
                    "mime_type": message.media.mime_type,
                    "caption": message.caption,
                    "content": b"",
                },
            )
            return
        self._pending_media[message.provider_message_id] = {
            "provider_message_id": message.provider_message_id,
            "media_id": message.media.media_id,
            "mime_type": message.media.mime_type,
            "caption": message.caption,
            "content": content,
        }

    async def _run_intake(self, message: NormalizedWhatsAppMessage, session: Any, store: Any) -> Any:
        text = message.text or message.caption
        if message.media and not text:
            return {
                "raw_text": "",
                "translated_text": "",
                "language": _cache_get(session, NV_LANGUAGE) or "unknown",
                "is_hazard_report": True,
                "qr_location": None,
                "qr_equipment": None,
                "session_id": getattr(session, "id", message.sender_id),
                "message_type": "image",
                "external_message_id": message.provider_message_id,
                "has_image": True,
            }
        return await self._intake()(
            message.sender_id,
            text,
            message_type="image" if message.media else "text",
            image_caption=message.caption if message.media else None,
            external_message_id=message.provider_message_id,
            session=session,
            session_store=store,
        )

    async def _run_incident_agent(self, intake_data: dict[str, Any], *, session: Any, canonical: dict[str, Any]) -> Any:
        previous = _as_dict(_cache_get(session, NV_DRAFT))
        draft = dict(intake_data)
        draft.update({k: v for k, v in canonical.items() if v is not None})
        if previous:
            for key, value in previous.items():
                if key not in draft or draft.get(key) in (None, "", []):
                    draft[key] = value
        return await self._incident()(
            draft,
            previous=previous or None,
            session=session,
            incident_id=canonical.get("incident_id") or draft.get("incident_id"),
        )

    async def _apply_duplicate_identity(
        self,
        duplicate: DuplicateResult,
        intake_data: dict[str, Any],
        message: NormalizedWhatsAppMessage,
        session: Any,
    ) -> dict[str, Any]:
        if duplicate.action not in {"reuse", "reopen"} or not duplicate.canonical_incident_id:
            return {}
        row = None
        if duplicate.canonical_uuid is not None and self.repository is not None:
            try:
                row = self.repository.get_incident(duplicate.canonical_uuid)
            except Exception:
                row = None
        mapping = _as_dict(row) if row is not None else {}
        ident = mapping.get("incident_ref") or duplicate.canonical_incident_id
        uuid = mapping.get("id") or duplicate.canonical_uuid
        count = int(mapping.get("duplicate_count") or duplicate.duplicate_count or 0)
        if self.repository is not None and uuid is not None and hasattr(self.repository, "increment_duplicate_count"):
            try:
                as_uuid = uuid if isinstance(uuid, UUID) else UUID(str(uuid))
                if count == 0:
                    updated = self.repository.increment_duplicate_count(as_uuid)
                    count = int(getattr(updated, "duplicate_count", 1) or 1)
                updated = self.repository.increment_duplicate_count(as_uuid)
                count = int(getattr(updated, "duplicate_count", count + 1) or count + 1)
                mapping = _as_dict(updated)
            except Exception:
                log.warning("duplicate_count_increment_failed")
        if duplicate.action == "reopen" and uuid is not None and self.repository is not None:
            try:
                as_uuid = uuid if isinstance(uuid, UUID) else UUID(str(uuid))
                self.repository.update_incident_status(as_uuid, "REOPENED")
            except Exception:
                log.warning("reopen_status_failed")
        status = to_display_status(mapping.get("status")) if mapping else duplicate.canonical_status
        if duplicate.action == "reopen":
            status = STATUS_IN_PROGRESS
        _cache_set(session, NV_CANONICAL, ident)
        _cache_set(session, NV_CANONICAL_UUID, str(uuid) if uuid else None)
        intake_data["incident_id"] = ident
        intake_data["id"] = str(uuid) if uuid else intake_data.get("id")
        intake_data["duplicate_count"] = count
        await self._audit(
            {"id": uuid, "incident_id": ident},
            "duplicate_report_linked",
            metadata={"provider_message_id": message.provider_message_id},
        )
        return {
            "incident_id": ident,
            "incident_ref": ident,
            "id": uuid,
            "duplicate_count": count,
            "status": status,
            "duplicate_detected": True,
            "preserve_status": duplicate.preserve_status,
            "location": mapping.get("location"),
            "hazard_category": mapping.get("hazard_category") or intake_data.get("hazard_category"),
            "assigned_team": mapping.get("assigned_team"),
        }

    async def _ensure_canonical_incident(
        self,
        merged: dict[str, Any],
        message: NormalizedWhatsAppMessage,
        session: Any,
    ) -> tuple[dict[str, Any], str | None]:
        if merged.get("duplicate_detected") and merged.get("incident_id"):
            return merged, None
        if merged.get("incident_id") and merged.get("id"):
            await self._transition(merged, STATUS_VALIDATING)
            return merged, None
        if merged.get("incident_id") and self.repository is None:
            return merged, None
        if self.repository is None:
            ref = merged.get("incident_id") or self._next_ref()
            merged["incident_id"] = ref
            merged["incident_ref"] = ref
            merged["status"] = STATUS_VALIDATING
            _cache_set(session, NV_CANONICAL, ref)
            return merged, None
        try:
            created = self.repository.create_incident(
                IncidentCreate(
                    incident_ref=merged.get("incident_id") or self._next_ref(),
                    reporter_id=message.sender_id,
                    source_channel="whatsapp",
                    session_id=str(getattr(session, "id", None) or message.sender_id),
                    detected_language=str(merged.get("language") or "") or None,
                    hazard_category=merged.get("hazard_category"),
                    hazard_description=merged.get("translated_text") or merged.get("clean_text") or merged.get("raw_text"),
                    location=merged.get("location") or merged.get("qr_location"),
                    injury_occurred=(
                        merged.get("already_injured") if isinstance(merged.get("already_injured"), bool) else None
                    ),
                    hazard_currently_active=(
                        merged.get("is_active") if isinstance(merged.get("is_active"), bool) else None
                    ),
                    people_exposed=(
                        merged.get("people_exposed") if isinstance(merged.get("people_exposed"), int) else None
                    ),
                    status=to_repository_status(STATUS_NEW),
                    original_message_id=message.provider_message_id,
                    original_message_text=merged.get("raw_text"),
                )
            )
            mapping = _as_dict(created)
            merged["id"] = mapping.get("id")
            merged["incident_id"] = mapping.get("incident_ref") or merged.get("incident_id")
            merged["incident_ref"] = merged["incident_id"]
            merged["duplicate_count"] = mapping.get("duplicate_count") or 0
            merged["status"] = STATUS_NEW
            _cache_set(session, NV_CANONICAL, merged["incident_id"])
            _cache_set(session, NV_CANONICAL_UUID, str(mapping.get("id")))
            await self._audit(merged, "incident_draft_started", new_status=STATUS_NEW)
            await self._transition(merged, STATUS_VALIDATING)
            self._trace("repository")
            return merged, None
        except Exception:
            log.warning("repository_update_failed")
            return merged, "repository_create_failed"

    async def _transition(self, merged: dict[str, Any], display_status: str) -> None:
        if merged.get("preserve_status") and merged.get("duplicate_detected"):
            return
        current = to_display_status(merged.get("status")) or STATUS_NEW
        if current == display_status:
            return
        ident = merged.get("id")
        uuid = _as_uuid(ident)
        repo_status = to_repository_status(display_status)
        if uuid is not None and self.repository is not None and hasattr(self.repository, "update_incident_status"):
            try:
                updated = self.repository.update_incident_status(uuid, repo_status)
                merged["status"] = to_display_status(getattr(updated, "status", repo_status)) or display_status
            except Exception:
                log.warning("repository_update_failed")
                merged["status"] = display_status
        else:
            merged["status"] = display_status
        await self._audit(merged, "status_transition", previous_status=current, new_status=display_status)

    async def _enrich_repository(self, merged: dict[str, Any]) -> None:
        uuid = _as_uuid(merged.get("id"))
        if uuid is None or self.repository is None or not hasattr(self.repository, "update_incident_fields"):
            return
        fields = {
            "hazard_category": merged.get("hazard_category"),
            "hazard_description": merged.get("translated_text") or merged.get("clean_text") or merged.get("raw_text"),
            "location": merged.get("location") or merged.get("qr_location"),
            "injury_occurred": (
                merged.get("already_injured") if isinstance(merged.get("already_injured"), bool) else None
            ),
            "hazard_currently_active": merged.get("is_active") if isinstance(merged.get("is_active"), bool) else None,
            "people_exposed": merged.get("people_exposed") if isinstance(merged.get("people_exposed"), int) else None,
            "current_risk_level": merged.get("current_risk_level") or (_as_dict(merged.get("risk")).get("level")),
            "detected_language": merged.get("language"),
            "original_message_text": merged.get("raw_text"),
            "session_id": merged.get("session_id"),
        }
        try:
            self.repository.update_incident_fields(uuid, fields)
        except Exception:
            log.warning("repository_update_failed")

    async def _audit(
        self,
        merged: dict[str, Any],
        update_type: str,
        *,
        message: str | None = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        uuid = _as_uuid(merged.get("id"))
        if uuid is None or self.repository is None or not hasattr(self.repository, "add_update"):
            return
        try:
            self.repository.add_update(
                IncidentUpdateCreate(
                    incident_id=uuid,
                    update_type=update_type,
                    previous_status=previous_status,
                    new_status=new_status,
                    actor_type="agent",
                    actor_reference="whatsapp_orchestrator",
                    message=message,
                    metadata=metadata,
                )
            )
        except Exception:
            log.warning("audit_event_failed type=%s", update_type)

    async def _pause_for_clarification(
        self,
        message: NormalizedWhatsAppMessage,
        session: Any,
        store: Any,
        merged: dict[str, Any],
    ) -> OrchestrationResult:
        question = merged.get("clarification_question") or "Where is this hazard?"
        last_for = _cache_get(session, "clarification_for_message_id")
        retry = last_for == message.provider_message_id
        sent = False
        existing_id = _cache_get(session, NV_CLARIFICATION_MSG)
        outbound_id = existing_id
        if retry:
            outbound_id = existing_id or message.provider_message_id
        else:
            previous_id = existing_id
            try:
                response = await self.whatsapp.send_clarification(
                    message.sender_id,
                    str(question),
                    reply_to_message_id=message.provider_message_id,
                )
                outbound_id = (response or {}).get("id") or f"clarification:{message.provider_message_id}"
                sent = True
                log.info("clarification_sent")
                self._note("clarifications")
            except WhatsAppSendError:
                log.warning("clarification_send_failed")
                outbound_id = f"clarification:{message.provider_message_id}"
            if previous_id and previous_id != outbound_id:
                self._complete_clarification_index(session, previous_id)
            _cache_set(session, "clarification_for_message_id", message.provider_message_id)
        _cache_set(session, NV_PENDING, True)
        _cache_set(session, NV_PENDING_FIELD, _infer_pending_field(question))
        _cache_set(session, NV_CLARIFICATION_MSG, outbound_id)
        _cache_set(session, NV_STAGE, "incident_clarification")
        index = dict(_cache_get(session, NV_CLARIFICATION_INDEX) or {})
        index[str(outbound_id)] = {"status": "pending", "incident_id": merged.get("incident_id")}
        _cache_set(session, NV_CLARIFICATION_INDEX, index)
        _cache_set(session, NV_DRAFT, _session_draft(merged))
        refs = list(_cache_get(session, NV_PENDING_MEDIA) or [])
        if message.media and message.provider_message_id not in refs:
            refs.append(message.provider_message_id)
            _cache_set(session, NV_PENDING_MEDIA, refs)
        _store_session(store, session)
        return self._result(
            message,
            session_id=getattr(session, "id", None),
            incident_id=merged.get("incident_id"),
            canonical_incident_id=merged.get("incident_id"),
            is_hazard_report=True,
            duplicate_detected=bool(merged.get("duplicate_detected")),
            clarification_required=True,
            clarification_sent=sent or retry,
            evidence_attached=False,
            status=to_display_status(merged.get("status")) or STATUS_VALIDATING,
        )

    def _complete_clarification_index(self, session: Any, message_id: Any) -> None:
        if not message_id:
            return
        index = dict(_cache_get(session, NV_CLARIFICATION_INDEX) or {})
        current = index.get(str(message_id))
        if isinstance(current, dict):
            current = dict(current)
            current["status"] = "completed"
            index[str(message_id)] = current
            _cache_set(session, NV_CLARIFICATION_INDEX, index)

    async def _handle_non_hazard(
        self,
        message: NormalizedWhatsAppMessage,
        session: Any,
        store: Any,
        intake_data: dict[str, Any],
    ) -> OrchestrationResult:
        try:
            await self.whatsapp.send_text_message(message.sender_id, NON_HAZARD_REPLY)
        except WhatsAppSendError:
            log.warning("non_hazard_ack_failed")
        _store_session(store, session)
        return self._result(
            message,
            session_id=intake_data.get("session_id") or getattr(session, "id", None),
            is_hazard_report=False,
        )

    async def _attach_followup_media(
        self,
        message: NormalizedWhatsAppMessage,
        session: Any,
        store: Any,
    ) -> OrchestrationResult:
        self._retain_media(message)
        merged = _as_dict(_cache_get(session, NV_DRAFT))
        merged["has_image"] = True
        merged["incident_id"] = merged.get("incident_id") or _cache_get(session, NV_CANONICAL)
        attached = await self.persist_initial_evidence(message, session, merged)
        if _cache_get(session, NV_PENDING):
            return await self.process_clarification_reply(message, session=session, store=store)
        _cache_set(session, NV_DRAFT, _session_draft(merged))
        _store_session(store, session)
        return self._result(
            message,
            session_id=getattr(session, "id", None),
            incident_id=merged.get("incident_id"),
            canonical_incident_id=merged.get("incident_id"),
            is_hazard_report=True,
            evidence_attached=attached,
            status=to_display_status(merged.get("status")),
        )

    def build_incident_record(self, merged: dict[str, Any]) -> dict[str, Any]:
        risk = _as_dict(merged.get("risk"))
        return {
            "incident_id": merged.get("incident_id") or merged.get("incident_ref"),
            "incident_ref": merged.get("incident_ref") or merged.get("incident_id"),
            "id": merged.get("id"),
            "raw_text": merged.get("raw_text"),
            "translated_text": merged.get("translated_text"),
            "language": merged.get("language"),
            "hazard_category": merged.get("hazard_category"),
            "location": merged.get("location") or merged.get("qr_location"),
            "equipment_involved": merged.get("equipment_involved") or merged.get("qr_equipment"),
            "people_exposed": merged.get("people_exposed"),
            "is_active": merged.get("is_active"),
            "already_injured": merged.get("already_injured"),
            "has_image": merged.get("has_image"),
            "qr_location": merged.get("qr_location"),
            "qr_equipment": merged.get("qr_equipment"),
            "source": merged.get("source")
            or ("QR_TAGGED" if merged.get("qr_location") or merged.get("qr_equipment") else None),
            "duplicate_count": merged.get("duplicate_count") or 1,
            "risk": risk,
            "risk_level": risk.get("level") or merged.get("current_risk_level"),
            "guidance": _as_dict(merged.get("guidance")),
            "assigned_team": merged.get("assigned_team"),
            "slack_channel_id": _as_dict(merged.get("slack_metadata")).get("slack_channel_id"),
            "slack_message_ts": _as_dict(merged.get("slack_metadata")).get("slack_message_ts"),
            "slack_thread_ts": _as_dict(merged.get("slack_metadata")).get("slack_thread_ts"),
            "status": merged.get("status"),
            "session_id": merged.get("session_id"),
            "recommended_action": merged.get("recommended_action"),
            "skip_clarification": merged.get("skip_clarification"),
        }

    def build_orchestration_result(
        self,
        message: NormalizedWhatsAppMessage,
        *,
        session: Any,
        merged: dict[str, Any],
        evidence_attached: bool,
        risk_completed: bool,
        guidance_generated: bool,
        guidance_sent: bool,
        coordination_completed: bool,
        error: str | None,
    ) -> OrchestrationResult:
        return self._result(
            message,
            session_id=getattr(session, "id", None) or merged.get("session_id"),
            incident_id=merged.get("incident_id"),
            canonical_incident_id=merged.get("incident_id"),
            is_hazard_report=True,
            duplicate_detected=bool(merged.get("duplicate_detected")),
            risk_completed=risk_completed,
            guidance_generated=guidance_generated,
            guidance_sent=guidance_sent,
            coordination_completed=coordination_completed,
            evidence_attached=evidence_attached,
            status=to_display_status(merged.get("status")),
            error=error,
        )


def _jsonable(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool, list, dict, type(None)))


def _session_draft(merged: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in merged.items():
        if isinstance(value, UUID):
            out[key] = str(value)
        elif _jsonable(value):
            out[key] = value
    return out


def _as_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _join_text(*parts: Any) -> str | None:
    texts = [str(part).strip() for part in parts if part]
    if not texts:
        return None
    seen: list[str] = []
    for item in texts:
        if item not in seen:
            seen.append(item)
    return "\n".join(seen)


def _infer_pending_field(question: str) -> str:
    lower = question.lower()
    if "where" in lower:
        return "location"
    if "still happening" in lower or "still" in lower:
        return "is_active"
    if "hazard" in lower:
        return "hazard_category"
    return "unknown"


_default_orchestrator: IncidentOrchestrator | None = None


def get_incident_orchestrator() -> IncidentOrchestrator:
    global _default_orchestrator
    if _default_orchestrator is None:
        _default_orchestrator = IncidentOrchestrator()
    return _default_orchestrator


async def process_incoming_whatsapp_message(
    message: NormalizedWhatsAppMessage | dict[str, Any],
    *,
    orchestrator: IncidentOrchestrator | None = None,
    whatsapp: WhatsAppCloudTransport | None = None,
    **kwargs: Any,
) -> OrchestrationResult:
    """Top-level use-case entry point for an inbound WhatsApp worker message."""
    orch = orchestrator
    if orch is None and kwargs:
        orch = IncidentOrchestrator(whatsapp=whatsapp, **kwargs)
    elif orch is None and whatsapp is not None:
        orch = IncidentOrchestrator(whatsapp=whatsapp)
    elif orch is None:
        orch = get_incident_orchestrator()
    return await orch.process_incoming_whatsapp_message(message)
