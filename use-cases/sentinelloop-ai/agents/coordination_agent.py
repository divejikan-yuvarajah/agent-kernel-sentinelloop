"""SentinelLoop coordination agent.

Deterministic team routing, Slack operational alerts, and assignment
lifecycle. Does not reclassify incidents, recalculate risk, or invent
guidance. Notification delivered is not human acknowledgement.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from integrations.slack_handler import (
    ACTION_ACCEPT,
    ACTION_CLOSED,
    ACTION_ESCALATE,
    ACTION_HANDOVER_ACK,
    ACTION_HANDOVER_ASSIGN,
    ACTION_HANDOVER_ESCALATE,
    ACTION_HANDOVER_VIEW,
    ACTION_REASSIGN,
    MESSAGE_INSPECTION_REQUEST,
    SlackHandler,
    SlackPostError,
    build_incident_blocks,
    build_inspection_request_blocks,
    extract_action,
    incident_fallback_text,
    inspection_request_fallback_text,
    is_bot_message,
    parse_thread_command,
)
from tools.assignment_tools import (
    DEFAULT_TEAM,
    INCIDENT_STATUS_MAP,
    STATUS_ACCEPTED,
    STATUS_ASSIGNED,
    STATUS_ESCALATED,
    STATUS_RESOLVED,
    VALID_TEAMS,
    extract_risk,
    get_assigned_team,
    load_team_destinations,
    resolve_escalation_destination,
    resolve_team_name,
    validate_status_transition,
)

ERROR_SLACK_POST = "slack_post_failed"
ERROR_CHANNEL = "slack_channel_not_configured"
ERROR_ACTION = "slack_action_invalid"
ERROR_NOT_FOUND = "incident_not_found"
ERROR_TRANSITION = "invalid_status_transition"
ERROR_TEAM = "unknown_reassignment_team"
ERROR_REPO = "repository_update_failed"
ERROR_DUPLICATE_EVENT = "duplicate_slack_event"
PERMANENT_OR_GENERIC = frozenset(
    {"channel_not_found", "invalid_auth", "not_in_channel", "invalid_arguments", ERROR_SLACK_POST}
)

log = logging.getLogger("sentinelloop.coordination")


class CoordinationRepository(Protocol):
    def get_incident(self, incident_id: UUID) -> Any: ...
    def update_incident_status(self, incident_id: UUID, status: str) -> Any: ...
    def add_update(self, data: Any) -> Any: ...
    def assign_incident(self, data: Any) -> Any: ...
    def get_assignment_for_incident(self, incident_id: UUID) -> Any: ...
    def update_assignment(self, assignment_id: UUID, fields: dict[str, Any]) -> Any: ...


class CoordinationRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    incident_id: str
    assigned_team: str = DEFAULT_TEAM
    original_assigned_team: str | None = None
    status: str = STATUS_ASSIGNED
    slack_channel_id: str | None = None
    slack_message_ts: str | None = None
    slack_thread_ts: str | None = None
    duplicate_count: int = 1
    delivery_status: str = "Pending"
    processed_events: list[str] = Field(default_factory=list)
    uuid: str | None = None
    assignment_id: str | None = None


class MemoryCoordinationStore:
    """In-process store used when a durable record is not yet loaded."""

    def __init__(self) -> None:
        self.records: dict[str, CoordinationRecord] = {}

    def get(self, incident_id: str) -> CoordinationRecord | None:
        return self.records.get(incident_id)

    def put(self, record: CoordinationRecord) -> CoordinationRecord:
        self.records[record.incident_id] = record
        return record


class CoordinationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    incident_id: str | None = None
    hazard_category: str | None = None
    assigned_team: str | None = None
    status: str | None = None
    slack_channel_id: str | None = None
    slack_message_ts: str | None = None
    slack_thread_ts: str | None = None
    duplicate_count: int = 1
    posted: bool = False
    interactive_actions_supported: bool = True
    available_actions: list[str] = Field(default_factory=lambda: ["accept", "reassign", "escalate", "closed"])
    coordination_error: str | None = None
    coordination_delivery_status: str = "Pending"
    slack_reply: str | None = None
    priority: str | None = None
    requires_acknowledgement: bool = False
    message_type: str | None = None
    location: str | None = None


def determine_assigned_team(category: str | None) -> str:
    return get_assigned_team(category)


def _as_mapping(incident: Any) -> dict[str, Any]:
    if incident is None:
        return {}
    if isinstance(incident, dict):
        return dict(incident)
    dump = getattr(incident, "model_dump", None)
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


def _description(mapping: dict[str, Any]) -> str | None:
    for key in ("translated_text", "raw_text", "hazard_description", "description"):
        value = mapping.get(key)
        if value:
            return str(value)
    return None


def _duplicate_count(mapping: dict[str, Any]) -> int:
    value = mapping.get("duplicate_count")
    try:
        return int(value) if value is not None else 1
    except (TypeError, ValueError):
        return 1


def _blocks_for(mapping: dict[str, Any], record: CoordinationRecord) -> list[dict[str, Any]]:
    level, explanation = extract_risk(mapping)
    return build_incident_blocks(
        incident_id=record.incident_id,
        category=str(mapping.get("hazard_category") or "other"),
        location=mapping.get("location"),
        description=_description(mapping),
        people_exposed=mapping.get("people_exposed"),
        risk_level=level,
        risk_explanation=explanation,
        recommended_action=mapping.get("recommended_action"),
        assigned_team=record.assigned_team,
        duplicate_count=record.duplicate_count,
        status=record.status,
        include_actions=record.status != STATUS_RESOLVED,
    )


def _priority(mapping: dict[str, Any]) -> str | None:
    level, _ = extract_risk(mapping)
    if (level or "").lower() == "critical" or mapping.get("skip_clarification") is True:
        return "urgent"
    return None


class CoordinationService:
    def __init__(
        self,
        *,
        slack: SlackHandler | None = None,
        repository: Any | None = None,
        store: MemoryCoordinationStore | None = None,
        destinations: dict[str, str] | None = None,
    ) -> None:
        self.slack = slack or SlackHandler(destinations=destinations or load_team_destinations())
        if destinations:
            self.slack.destinations = destinations
        self.repository = repository
        self.store = store or MemoryCoordinationStore()

    def _record(self, incident_id: str) -> CoordinationRecord:
        found = self.store.get(incident_id)
        if found:
            return found
        return CoordinationRecord(incident_id=incident_id)

    def _event_already_processed(self, record: CoordinationRecord, event_id: str | None) -> bool:
        return bool(event_id) and event_id in record.processed_events

    def _mark_event(self, record: CoordinationRecord, event_id: str | None) -> None:
        if not event_id or event_id in record.processed_events:
            return
        record.processed_events.append(event_id)
        if len(record.processed_events) > 200:
            record.processed_events = record.processed_events[-200:]
        self.store.put(record)

    def _mark_if_committed(self, record: CoordinationRecord, event_id: str | None, result: CoordinationResult) -> None:
        if result.coordination_error == ERROR_REPO:
            return
        self._mark_event(record, event_id)

    def _persist_status(
        self,
        record: CoordinationRecord,
        actor: str | None,
        event_type: str,
        *,
        previous_status: str | None = None,
    ) -> None:
        if self.repository is None:
            return
        uuid_raw = record.uuid
        try:
            incident_uuid = UUID(str(uuid_raw)) if uuid_raw else None
        except (TypeError, ValueError):
            incident_uuid = None
        if incident_uuid is None:
            return
        from database.schemas import IncidentUpdateCreate

        mapped = INCIDENT_STATUS_MAP.get(record.status, "ASSIGNED")
        try:
            self.repository.update_incident_status(incident_uuid, mapped)
            if record.assignment_id:
                fields: dict[str, Any] = {"assignment_status": record.status, "team": record.assigned_team}
                if record.slack_channel_id:
                    fields["slack_channel_id"] = record.slack_channel_id
                self.repository.update_assignment(UUID(record.assignment_id), fields)
            self.repository.add_update(
                IncidentUpdateCreate(
                    incident_id=incident_uuid,
                    update_type=event_type,
                    previous_status=previous_status,
                    new_status=record.status,
                    actor_type="safety_officer",
                    actor_reference=actor,
                    metadata={
                        "source": "slack",
                        "assigned_team": record.assigned_team,
                        "original_assigned_team": record.original_assigned_team,
                        "slack_message_ts": record.slack_message_ts,
                        "slack_channel_id": record.slack_channel_id,
                        "slack_thread_ts": record.slack_thread_ts,
                    },
                )
            )
        except Exception:
            log.exception("repository_update_failed event=%s", event_type)
            raise

    async def coordinate_incident(self, incident: Any) -> CoordinationResult:
        started = time.monotonic()
        log.info("coordination_started")
        mapping = _as_mapping(incident)
        incident_id = _incident_key(mapping)
        if not incident_id:
            return CoordinationResult(posted=False, coordination_error=ERROR_NOT_FOUND)
        category = mapping.get("hazard_category")
        team = determine_assigned_team(category)
        log.info("team_mapped team=%s", team)
        record = self._record(incident_id)
        if not record.original_assigned_team:
            record.original_assigned_team = team
        if record.status == STATUS_ASSIGNED and not record.slack_message_ts:
            record.assigned_team = team
        record.duplicate_count = _duplicate_count(mapping)
        if mapping.get("id"):
            record.uuid = str(mapping["id"])
        level, _ = extract_risk(mapping)
        result = CoordinationResult(
            incident_id=incident_id,
            hazard_category=str(category) if category is not None else None,
            assigned_team=record.assigned_team,
            status=record.status,
            duplicate_count=record.duplicate_count,
            interactive_actions_supported=True,
            priority=_priority(mapping),
            requires_acknowledgement=(level or "") in {"High", "Critical"},
        )
        channel = self.slack.channel_for_team(record.assigned_team)
        if not channel:
            result.coordination_error = ERROR_CHANNEL
            result.coordination_delivery_status = "Failed"
            record.delivery_status = "Failed"
            self.store.put(record)
            log.warning("slack_incident_post_failed reason=channel_not_configured")
            return result

        blocks = _blocks_for(mapping, record)
        fallback = incident_fallback_text(
            {"incident_id": incident_id, "category": category, "assigned_team": record.assigned_team}
        )
        if record.slack_message_ts:
            try:
                await self.slack.update_incident_message(
                    channel=record.slack_channel_id or channel,
                    ts=record.slack_message_ts,
                    blocks=blocks,
                    text=fallback,
                )
                result.posted = True
                result.slack_channel_id = record.slack_channel_id or channel
                result.slack_message_ts = record.slack_message_ts
                result.slack_thread_ts = record.slack_thread_ts
                result.coordination_delivery_status = "Delivered"
            except SlackPostError as exc:
                result.coordination_error = exc.code
                result.coordination_delivery_status = "Failed"
            self.store.put(record)
            result.status = record.status
            result.assigned_team = record.assigned_team
            return result

        try:
            posted = await self.slack.post_incident_message(channel=channel, blocks=blocks, text=fallback)
        except SlackPostError as exc:
            log.warning("slack_incident_post_failed code=%s", exc.code)
            record.delivery_status = "Failed"
            self.store.put(record)
            result.coordination_error = exc.code if exc.code in PERMANENT_OR_GENERIC else ERROR_SLACK_POST
            result.coordination_delivery_status = "Failed"
            result.status = record.status
            return result

        record.slack_channel_id = posted.get("channel") or channel
        record.slack_message_ts = posted.get("ts")
        record.slack_thread_ts = posted.get("ts")
        record.delivery_status = "Delivered"
        record.status = STATUS_ASSIGNED
        self.store.put(record)
        if self.repository is not None and record.uuid:
            try:
                from database.schemas import AssignmentCreate, IncidentUpdateCreate

                assignment = self.repository.assign_incident(
                    AssignmentCreate(
                        incident_id=UUID(record.uuid),
                        team=record.assigned_team,
                        slack_channel_id=record.slack_channel_id,
                        assignment_status=STATUS_ASSIGNED,
                    )
                )
                record.assignment_id = str(getattr(assignment, "id", "") or "")
                self.repository.update_incident_status(UUID(record.uuid), "ASSIGNED")
                self.repository.add_update(
                    IncidentUpdateCreate(
                        incident_id=UUID(record.uuid),
                        update_type="incident_assigned",
                        new_status=STATUS_ASSIGNED,
                        actor_type="agent",
                        metadata={
                            "slack_message_ts": record.slack_message_ts,
                            "slack_channel_id": record.slack_channel_id,
                            "assigned_team": record.assigned_team,
                        },
                    )
                )
            except Exception:
                log.exception("repository_update_failed during coordinate")
        result.posted = True
        result.status = record.status
        result.assigned_team = record.assigned_team
        result.slack_channel_id = record.slack_channel_id
        result.slack_message_ts = record.slack_message_ts
        result.slack_thread_ts = record.slack_thread_ts
        result.coordination_delivery_status = "Delivered"
        log.info(
            "slack_incident_posted ts=%s latency_ms=%s",
            record.slack_message_ts,
            int((time.monotonic() - started) * 1000),
        )
        return result

    async def _apply_status(
        self,
        record: CoordinationRecord,
        target: str,
        *,
        actor: str | None,
        event_type: str,
        mapping: dict[str, Any] | None = None,
        thread_message: str,
    ) -> CoordinationResult:
        outcome = validate_status_transition(record.status, target)
        result = CoordinationResult(
            incident_id=record.incident_id,
            assigned_team=record.assigned_team,
            status=record.status,
            slack_channel_id=record.slack_channel_id,
            slack_message_ts=record.slack_message_ts,
            slack_thread_ts=record.slack_thread_ts,
            posted=bool(record.slack_message_ts),
        )
        if outcome == "invalid":
            result.coordination_error = ERROR_TRANSITION
            result.slack_reply = (
                "This incident is already resolved."
                if record.status == STATUS_RESOLVED
                else "This action is not valid for the current status."
            )
            log.info("invalid_status_transition from=%s to=%s", record.status, target)
            if record.slack_channel_id and record.slack_thread_ts:
                try:
                    await self.slack.post_thread_reply(
                        channel=record.slack_channel_id, thread_ts=record.slack_thread_ts, text=result.slack_reply
                    )
                except SlackPostError:
                    pass
            return result
        if outcome == "noop":
            result.slack_reply = f"Incident already {target.lower()}."
            return result
        previous = record.status
        record.status = target
        try:
            self._persist_status(record, actor, event_type, previous_status=previous)
        except Exception:
            record.status = previous
            result.coordination_error = ERROR_REPO
            result.slack_reply = "Unable to update the incident record. Please retry."
            return result
        self.store.put(record)
        result.status = record.status
        result.slack_reply = thread_message
        if record.slack_channel_id and record.slack_thread_ts:
            try:
                await self.slack.post_thread_reply(
                    channel=record.slack_channel_id, thread_ts=record.slack_thread_ts, text=thread_message
                )
                if mapping is not None:
                    await self.slack.update_incident_message(
                        channel=record.slack_channel_id,
                        ts=record.slack_message_ts or record.slack_thread_ts,
                        blocks=_blocks_for(mapping, record),
                        text=incident_fallback_text(
                            {"incident_id": record.incident_id, "assigned_team": record.assigned_team}
                        ),
                    )
            except SlackPostError:
                log.warning("slack presentation update failed after repository success")
        return result

    async def accept_incident(
        self, incident_id: str, *, actor: str | None = None, mapping: dict[str, Any] | None = None
    ) -> CoordinationResult:
        record = self._record(incident_id)
        result = await self._apply_status(
            record,
            STATUS_ACCEPTED,
            actor=actor,
            event_type="incident_accepted",
            mapping=mapping,
            thread_message="Incident accepted.",
        )
        if result.coordination_error is None and result.status == STATUS_ACCEPTED:
            log.info("incident_accepted incident=%s", incident_id)
        return result

    async def reassign_incident(
        self,
        incident_id: str,
        team: str,
        *,
        actor: str | None = None,
        mapping: dict[str, Any] | None = None,
    ) -> CoordinationResult:
        resolved = resolve_team_name(team)
        record = self._record(incident_id)
        result = CoordinationResult(incident_id=incident_id, assigned_team=record.assigned_team, status=record.status)
        if resolved is None or resolved not in VALID_TEAMS:
            result.coordination_error = ERROR_TEAM
            result.slack_reply = "Unknown team. Use a configured destination team."
            return result
        previous = record.assigned_team
        record.assigned_team = resolved
        if self.repository is not None:
            try:
                self._persist_status(record, actor, "incident_reassigned", previous_status=record.status)
            except Exception:
                record.assigned_team = previous
                result.coordination_error = ERROR_REPO
                result.slack_reply = "Unable to update the incident record. Please retry."
                return result
        self.store.put(record)
        text = f"Reassigned from {previous} to {resolved}."
        result.assigned_team = resolved
        result.slack_reply = text
        log.info("incident_reassigned from=%s to=%s", previous, resolved)
        dest = self.slack.channel_for_team(resolved)
        if record.slack_channel_id and record.slack_thread_ts:
            try:
                await self.slack.post_thread_reply(
                    channel=record.slack_channel_id, thread_ts=record.slack_thread_ts, text=text
                )
            except SlackPostError:
                pass
        if dest and dest != record.slack_channel_id:
            try:
                await self.slack.post_incident_message(
                    channel=dest,
                    blocks=_blocks_for(mapping or {"hazard_category": "other"}, record) if mapping else [],
                    text=text,
                )
            except SlackPostError:
                pass
        return result

    async def escalate_incident(
        self, incident_id: str, *, actor: str | None = None, mapping: dict[str, Any] | None = None
    ) -> CoordinationResult:
        record = self._record(incident_id)
        if record.status == STATUS_ESCALATED:
            result = CoordinationResult(
                incident_id=incident_id,
                status=STATUS_ESCALATED,
                assigned_team=record.assigned_team,
                slack_reply="Incident already escalated.",
            )
            return result
        result = await self._apply_status(
            record,
            STATUS_ESCALATED,
            actor=actor,
            event_type="incident_escalated",
            mapping=mapping,
            thread_message="Status: Escalated",
        )
        dest = resolve_escalation_destination(self.slack.destinations)
        if dest and result.coordination_error is None:
            try:
                await self.slack.post_incident_message(
                    channel=dest,
                    blocks=_blocks_for(mapping or {}, record) if mapping else [],
                    text=f"Escalated incident {incident_id}",
                )
            except SlackPostError:
                log.warning("escalation destination post failed")
        log.info("incident_escalated incident=%s", incident_id)
        return result

    async def update_incident_status(
        self, incident_id: str, status: str, *, actor: str | None = None, mapping: dict[str, Any] | None = None
    ) -> CoordinationResult:
        record = self._record(incident_id)
        event = "incident_resolved" if status == STATUS_RESOLVED else "incident_in_progress"
        message = "✅ Resolved" if status == STATUS_RESOLVED else "Status: In Progress"
        result = await self._apply_status(
            record, status, actor=actor, event_type=event, mapping=mapping, thread_message=message
        )
        if status == STATUS_RESOLVED and result.coordination_error is None:
            await self._trigger_followup(record, mapping, actor)
        return result

    async def close_incident_human(
        self,
        incident_id: str,
        *,
        actor: str | None = None,
        action_id: str | None = None,
        thread_ts: str | None = None,
        channel_id: str | None = None,
        mapping: dict[str, Any] | None = None,
        message: dict[str, Any] | None = None,
    ) -> CoordinationResult:
        # SPEC.md Rule: Human intervention for Critical incidents; explicit Slack Closed.
        record = self._record(incident_id)
        result = CoordinationResult(
            incident_id=incident_id,
            assigned_team=record.assigned_team,
            status=record.status,
            slack_channel_id=record.slack_channel_id,
            slack_message_ts=record.slack_message_ts,
            slack_thread_ts=record.slack_thread_ts,
            posted=bool(record.slack_message_ts),
        )
        from guardrails.output_validation import validate_slack_closure

        slack = validate_slack_closure(
            action="Closed",
            actor=actor,
            incident_id=incident_id,
            expected_incident_id=record.incident_id or incident_id,
            thread_ts=thread_ts,
            expected_thread_ts=record.slack_thread_ts,
            channel_id=channel_id,
            expected_channel_id=record.slack_channel_id,
            is_bot=False,
        )
        if not slack.get("approved"):
            result.coordination_error = ERROR_ACTION
            result.slack_reply = "Closed is only accepted from an authorized officer in this incident thread."
            return result
        evidence = {
            "closed_by": actor,
            "source": "slack",
            "action": "Closed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "slack_action_id": action_id or ACTION_CLOSED,
        }
        risk_level = None
        if mapping:
            risk = mapping.get("risk") if isinstance(mapping.get("risk"), dict) else mapping
            if isinstance(risk, dict):
                risk_level = risk.get("risk_level") or risk.get("final_risk_level") or mapping.get("risk_level")
        from agents.followup_agent import FollowupRecord, get_followup_service
        from tools.lifecycle import STATUS_AWAITING_VERIFICATION, STATUS_CLOSED, STATUS_RESOLVED

        followup = getattr(self, "followup", None) or get_followup_service()
        existing = followup.store.get(incident_id)
        display = record.status
        if existing is None and display not in {STATUS_RESOLVED, STATUS_AWAITING_VERIFICATION, STATUS_CLOSED}:
            result.coordination_error = ERROR_TRANSITION
            result.slack_reply = "This incident is not in a closable state."
            return result
        if existing is None:
            followup.store.put(
                FollowupRecord(
                    incident_id=incident_id,
                    uuid=record.uuid,
                    status=STATUS_RESOLVED,
                    assigned_team=record.assigned_team,
                    slack_channel_id=record.slack_channel_id,
                    slack_thread_ts=record.slack_thread_ts,
                    risk_level=risk_level,
                    reviewed_by_human=True,
                    slack_closed_action=evidence,
                )
            )
        closed = await followup.confirm_safe_and_close(incident_id, actor=actor, source="slack", slack_closure=evidence)
        if closed.error:
            result.coordination_error = closed.error
            result.slack_reply = closed.worker_reply or "Closure was blocked by the safety guardrail."
            result.status = closed.status or record.status
            return result
        record.status = STATUS_CLOSED
        self.store.put(record)
        result.status = STATUS_CLOSED
        result.slack_reply = "Incident closed by authorized officer."
        if record.slack_channel_id and record.slack_thread_ts:
            try:
                await self.slack.post_thread_reply(
                    channel=record.slack_channel_id,
                    thread_ts=record.slack_thread_ts,
                    text=result.slack_reply,
                )
            except SlackPostError:
                log.warning("slack close acknowledgement failed")
        return result

    async def _trigger_followup(
        self, record: CoordinationRecord, mapping: dict[str, Any] | None, actor: str | None
    ) -> None:
        try:
            from agents.followup_agent import start_worker_verification

            payload = dict(mapping or {})
            payload.setdefault("incident_id", record.incident_id)
            payload.setdefault("incident_ref", record.incident_id)
            payload["status"] = STATUS_RESOLVED
            payload["assigned_team"] = record.assigned_team
            payload["slack_channel_id"] = record.slack_channel_id
            payload["slack_thread_ts"] = record.slack_thread_ts
            if record.uuid:
                payload.setdefault("id", record.uuid)
            await start_worker_verification(payload, actor=actor)
        except Exception:
            log.exception("followup trigger failed incident=%s", record.incident_id)

    async def handle_thread_event(
        self, event: dict[str, Any], *, mapping_lookup: dict[str, dict[str, Any]] | None = None
    ) -> CoordinationResult | None:
        if is_bot_message(event, self.slack.bot_user_id):
            return None
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return None
        event_id = str(event.get("event_id") or event.get("client_msg_id") or event.get("ts") or "") or None
        record = next(
            (
                r
                for r in self.store.records.values()
                if r.slack_thread_ts == thread_ts or r.slack_message_ts == thread_ts
            ),
            None,
        )
        if record is None:
            command = parse_thread_command(event.get("text"))
            if command and str(command.get("command") or "").startswith("handover_"):
                from agents.handover_agent import handle_handover_thread_command

                await handle_handover_thread_command(event, command)
            return None
        command = parse_thread_command(event.get("text"))
        if command is None:
            return None
        if self._event_already_processed(record, event_id):
            log.info("slack_duplicate_event_ignored")
            return CoordinationResult(
                incident_id=record.incident_id, coordination_error=ERROR_DUPLICATE_EVENT, status=record.status
            )
        actor = event.get("user")
        mapping = (mapping_lookup or {}).get(record.incident_id)
        log.info("slack_action_received command=%s", command.get("command"))
        result: CoordinationResult | None = None
        if command["command"] == "accept":
            result = await self.accept_incident(record.incident_id, actor=actor, mapping=mapping)
        elif command["command"] == "escalate":
            result = await self.escalate_incident(record.incident_id, actor=actor, mapping=mapping)
        elif command["command"] == "reassign":
            if command.get("invalid"):
                result = CoordinationResult(
                    incident_id=record.incident_id, coordination_error=ERROR_TEAM, slack_reply="Unknown team."
                )
            else:
                result = await self.reassign_incident(record.incident_id, command["team"], actor=actor, mapping=mapping)
        elif command["command"] == "set_status":
            result = await self.update_incident_status(
                record.incident_id, command["status"], actor=actor, mapping=mapping
            )
        elif command["command"] == "close":
            result = await self.close_incident_human(
                record.incident_id,
                actor=actor,
                action_id=ACTION_CLOSED,
                thread_ts=thread_ts,
                channel_id=event.get("channel") or event.get("channel_id"),
                mapping=mapping,
            )
        if result is not None:
            self._mark_if_committed(record, event_id, result)
        return result

    async def handle_interactive_action(
        self, payload: dict[str, Any], *, mapping: dict[str, Any] | None = None
    ) -> CoordinationResult:
        action_id, incident_id, selected_team = extract_action(payload)
        if action_id in {ACTION_HANDOVER_ACK, ACTION_HANDOVER_ASSIGN, ACTION_HANDOVER_ESCALATE, ACTION_HANDOVER_VIEW}:
            from agents.handover_agent import handle_handover_action

            actor = (payload.get("user") or {}).get("id") if isinstance(payload.get("user"), dict) else None
            await handle_handover_action(action_id, incident_id or "", actor=actor)
            return CoordinationResult(incident_id=incident_id or "", slack_reply="Handover action recorded.")
        if not incident_id or not action_id:
            return CoordinationResult(coordination_error=ERROR_ACTION)
        record = self._record(incident_id)
        event_id = str(payload.get("trigger_id") or payload.get("action_ts") or payload.get("event_id") or "") or None
        if self._event_already_processed(record, event_id):
            return CoordinationResult(
                incident_id=incident_id, coordination_error=ERROR_DUPLICATE_EVENT, status=record.status
            )
        actor = (payload.get("user") or {}).get("id") if isinstance(payload.get("user"), dict) else None
        log.info("slack_action_received action=%s", action_id)
        if action_id == ACTION_ACCEPT:
            result = await self.accept_incident(incident_id, actor=actor, mapping=mapping)
        elif action_id == ACTION_ESCALATE:
            result = await self.escalate_incident(incident_id, actor=actor, mapping=mapping)
        elif action_id == ACTION_REASSIGN:
            team = selected_team or ""
            if not team:
                result = CoordinationResult(
                    incident_id=incident_id,
                    slack_reply="Reply with reassign: <configured team name>.",
                    status=record.status,
                )
            else:
                result = await self.reassign_incident(incident_id, team, actor=actor, mapping=mapping)
        elif action_id == ACTION_CLOSED:
            message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
            result = await self.close_incident_human(
                incident_id,
                actor=actor,
                action_id=action_id,
                thread_ts=(
                    payload.get("message", {}).get("thread_ts")
                    if isinstance(payload.get("message"), dict)
                    else payload.get("thread_ts") or record.slack_thread_ts
                ),
                channel_id=(
                    payload.get("channel", {}).get("id")
                    if isinstance(payload.get("channel"), dict)
                    else payload.get("channel") or record.slack_channel_id
                ),
                mapping=mapping,
                message=message,
            )
        else:
            result = CoordinationResult(incident_id=incident_id, coordination_error=ERROR_ACTION)
        self._mark_if_committed(record, event_id, result)
        return result

    async def request_inspection(self, payload: dict[str, Any]) -> CoordinationResult:
        """Post a preventive inspection Slack note. Does not schedule or mutate incidents."""
        location = str(payload.get("location") or "Unknown location")
        reason = str(payload.get("reason") or "Recurring hazard pattern detected.")
        recommendation = str(payload.get("recommendation") or "Schedule safety inspection.")
        category = payload.get("category")
        team = determine_assigned_team(str(category) if category else None)
        result = CoordinationResult(
            location=location,
            hazard_category=str(category) if category else None,
            assigned_team=team,
            message_type=MESSAGE_INSPECTION_REQUEST,
            priority="Attention Needed",
        )
        channel = self.slack.channel_for_team(team)
        if not channel:
            result.coordination_error = ERROR_CHANNEL
            result.coordination_delivery_status = "Failed"
            log.warning("inspection_requested location=%s posted=false reason=channel_not_configured", location)
            return result
        blocks = build_inspection_request_blocks(
            location=location,
            reason=reason,
            recommended_action=recommendation,
            category=str(category) if category else None,
        )
        fallback = inspection_request_fallback_text(location=location, reason=reason)
        try:
            posted = await self.slack.post_incident_message(channel=channel, blocks=blocks, text=fallback)
        except SlackPostError as exc:
            result.coordination_error = exc.code if exc.code in PERMANENT_OR_GENERIC else ERROR_SLACK_POST
            result.coordination_delivery_status = "Failed"
            log.warning("inspection_requested location=%s posted=false code=%s", location, exc.code)
            return result
        result.posted = True
        result.slack_channel_id = posted.get("channel") or channel
        result.slack_message_ts = posted.get("ts")
        result.coordination_delivery_status = "Delivered"
        log.info("inspection_requested location=%s posted=true", location)
        return result


_default_service: CoordinationService | None = None


def get_coordination_service() -> CoordinationService:
    global _default_service
    if _default_service is None:
        _default_service = CoordinationService()
    return _default_service


async def coordinate_incident(incident: Any, *, service: CoordinationService | None = None) -> CoordinationResult:
    return await (service or get_coordination_service()).coordinate_incident(incident)


async def request_inspection(
    payload: dict[str, Any] | None = None,
    *,
    service: CoordinationService | None = None,
) -> CoordinationResult:
    return await (service or get_coordination_service()).request_inspection(payload or {})


async def coordinate_incident_alert(incident_json: str) -> str:
    """Post a Slack coordination card. Call after guidance_agent."""
    from agentkernel.core import ToolContext

    ctx = ToolContext.get()
    session = ctx.session
    cache = session.get_non_volatile_cache()
    draft: dict[str, Any] = {}
    for key in ("incident_draft", "last_risk_assessment", "last_guidance_result"):
        cached = cache.get(key) if hasattr(cache, "get") else None
        if isinstance(cached, dict):
            if key == "last_risk_assessment":
                draft["risk"] = cached
            else:
                draft.update(cached)
    if incident_json and str(incident_json).strip():
        try:
            parsed = json.loads(incident_json)
            if isinstance(parsed, dict):
                draft.update(parsed)
        except json.JSONDecodeError:
            pass
    result = await coordinate_incident(draft)
    cache.set("last_coordination_result", json.loads(result.model_dump_json()))
    return result.model_dump_json()


def create_coordination_agent(*, model: Any = None, handoffs: list[Any] | None = None) -> Any:
    from agentkernel.openai import OpenAIToolBuilder

    from ak_bootstrap import pin_openai_agents_sdk

    pin_openai_agents_sdk()
    from agents import Agent  # type: ignore[attr-defined]

    tools = OpenAIToolBuilder.bind([coordinate_incident_alert])
    kwargs: dict[str, Any] = {}
    if model is not None:
        kwargs["model"] = model
    if handoffs:
        kwargs["handoffs"] = handoffs
    return Agent(
        name="coordination_agent",
        handoff_description="Routes incidents to the safety team and records assignment intent.",
        instructions=(
            "You are coordination_agent. Call coordinate_incident_alert with the structured incident JSON. "
            "Return that JSON. Do not treat a Slack post as human acknowledgement. "
            "Do not recompute risk or invent safety procedures. "
            "Handoff to followup_agent when the worker should be asked to verify a fix."
        ),
        tools=tools,
        **kwargs,
    )
