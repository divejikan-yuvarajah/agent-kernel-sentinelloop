"""Assemble a read-only explainable-AI audit packet from persisted records.

Does not import agents, mutate incidents, or re-run intake/risk/guidance.
``calculate_risk`` is called only to restate stored severity/likelihood against
the deterministic engine for inspectors.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from dashboard.schemas import (
    AUDIT_EXPORT_VERSION,
    AuditAiDecision,
    AuditAssignmentChange,
    AuditCoordinationEvent,
    AuditExport,
    AuditExtractedInformation,
    AuditGuidanceItem,
    AuditIncidentInformation,
    AuditLanguageProcessing,
    AuditMetadata,
    AuditOriginalReport,
    AuditResolution,
    AuditRiskAnalysis,
    AuditTimelineEvent,
    ExtractedField,
)
from dashboard.service import (
    _ROLE_AGENT,
    _as_decimal,
    _as_float,
    _as_str,
    _aware,
    _read_json,
    _safe_storage_available,
    _utcnow,
    format_elapsed,
    incident_title,
    mask_reporter,
    normalize_risk_level,
    officer_label,
    redact_text,
)
from database.models import Assignment, Incident, IncidentEvidence, IncidentUpdate, RiskAssessment
from tools.lifecycle import to_display_status
from tools.qr_tags import extract_qr_origin
from tools.risk_tools import RiskInputError, calculate_risk

log = logging.getLogger("sentinelloop.dashboard.audit")

_CHANNEL_LABEL = {
    "whatsapp": "WhatsApp",
    "slack": "Slack",
    "telegram": "Telegram",
}
_LANGUAGE_NAME = {
    "si": "Sinhala",
    "ta": "Tamil",
    "en": "English",
    "sinhala": "Sinhala",
    "tamil": "Tamil",
    "english": "English",
}
_SECRET_KEY_FRAGMENTS = ("api_key", "access_token", "authorization", "secret", "password", "service_role")
_GUIDANCE_TYPES = frozenset(
    {"guidance_sent", "guidance_generated", "worker_guidance", "guidance_send_failed", "approved_guidance"}
)
_COORD_TYPES = frozenset(
    {
        "slack_coordination_completed",
        "slack_coordination_failed",
        "incident_assigned",
        "officer_notified",
        "escalation_sent",
        "team_renotified",
    }
)
_RESOLUTION_TYPES = frozenset(
    {
        "incident_closed",
        "incident_resolved",
        "worker_confirmed",
        "worker_verification_confirmed",
        "status_transition",
    }
)


def _channel_label(value: str | None) -> str | None:
    if not value:
        return None
    return _CHANNEL_LABEL.get(value.strip().lower(), value.strip())


def _language_name(code: str | None) -> str | None:
    if not code:
        return None
    key = code.strip().lower()
    return _LANGUAGE_NAME.get(key, code.strip())


def _severity_label(value: int | None) -> str | None:
    if value is None:
        return None
    if value >= 5:
        return "CRITICAL"
    if value >= 4:
        return "HIGH"
    if value >= 3:
        return "MEDIUM"
    return "LOW"


def _likelihood_label(value: int | None) -> str | None:
    if value is None:
        return None
    if value >= 5:
        return "ALMOST_CERTAIN"
    if value >= 4:
        return "LIKELY"
    if value >= 3:
        return "POSSIBLE"
    if value >= 2:
        return "UNLIKELY"
    return "RARE"


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS):
                continue
            cleaned[str(key)] = _scrub(item)
        return cleaned
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _meta(update: IncidentUpdate) -> dict[str, Any]:
    raw = update.metadata if isinstance(update.metadata, dict) else {}
    scrubbed = _scrub(raw)
    return scrubbed if isinstance(scrubbed, dict) else {}


def _sort_updates(updates: list[IncidentUpdate]) -> list[IncidentUpdate]:
    return sorted(updates, key=lambda row: _aware(row.created_at) or datetime.min.replace(tzinfo=timezone.utc))


def _extracted(incident: Incident, origin: dict[str, Any]) -> AuditExtractedInformation:
    location_conf = 1.0 if origin.get("location_verified") else None
    equipment = origin.get("qr_equipment") or incident.site_id
    rows = [
        ExtractedField(field="hazard_type", value=incident.hazard_category),
        ExtractedField(field="category", value=incident.hazard_category),
        ExtractedField(field="location", value=incident.location, confidence=location_conf),
        ExtractedField(field="equipment", value=str(equipment) if equipment else None, confidence=location_conf),
        ExtractedField(
            field="urgency_indicators",
            value="active hazard" if incident.hazard_currently_active else None,
        ),
        ExtractedField(
            field="affected_people",
            value=str(incident.people_exposed) if incident.people_exposed is not None else None,
        ),
        ExtractedField(
            field="injury_occurred",
            value="yes" if incident.injury_occurred else ("no" if incident.injury_occurred is False else None),
        ),
        ExtractedField(
            field="environmental_factors",
            value="hazard currently active" if incident.hazard_currently_active else None,
        ),
    ]
    return AuditExtractedInformation(fields=[row for row in rows if row.value])


def _ai_decision(
    incident: Incident,
    assessment: RiskAssessment | None,
    updates: list[IncidentUpdate],
) -> AuditAiDecision:
    detected: list[str] = []
    if incident.hazard_category:
        detected.append(incident.hazard_category)
    if incident.hazard_currently_active:
        detected.append("Hazard currently active")
    if incident.injury_occurred:
        detected.append("Injury reported")
    if incident.people_exposed:
        detected.append(f"People exposed: {incident.people_exposed}")
    if incident.duplicate_count and incident.duplicate_count > 1:
        detected.append(f"Repeated reports ({incident.duplicate_count})")
    confidence = None
    reasoning = None
    ai_level = None
    if assessment is not None:
        ai_level = normalize_risk_level(assessment.final_risk_level or assessment.base_risk_level)
        reasoning = redact_text(
            " ".join(part for part in (assessment.severity_reason, assessment.likelihood_reason) if part)
        )
        if assessment.severity is not None and assessment.likelihood is not None:
            confidence = round(min(0.99, (assessment.severity + assessment.likelihood) / 10), 2)
        for item in assessment.applied_overrides or []:
            if item and str(item) not in detected:
                detected.append(str(item))
    human = normalize_risk_level(incident.current_risk_level)
    override_reason = None
    for update in reversed(updates):
        meta = _meta(update)
        if meta.get("override_reason") or meta.get("human_override"):
            override_reason = redact_text(
                str(meta.get("override_reason") or meta.get("reason") or update.message or "")
            )
            break
        if update.actor_type == "safety_officer" and (update.update_type or "").lower().find("risk") >= 0:
            override_reason = redact_text(update.message)
            break
    overridden = bool(ai_level and human and ai_level != human)
    explanation = None
    if reasoning:
        explanation = f"Risk classified {human or ai_level or 'UNKNOWN'} because: {reasoning}"
    elif detected:
        explanation = f"Risk classified {human or 'UNKNOWN'} because: {'; '.join(detected)}"
    return AuditAiDecision(
        severity=_severity_label(assessment.severity if assessment else None),
        likelihood=_likelihood_label(assessment.likelihood if assessment else None),
        confidence=confidence,
        detected_risks=detected,
        reasoning_summary=reasoning,
        ai_recommendation=ai_level,
        human_final_decision=human,
        override_reason=override_reason if overridden or override_reason else None,
        explanation_label=explanation,
    )


def _risk_analysis(incident: Incident, assessment: RiskAssessment | None) -> AuditRiskAnalysis:
    score = assessment.risk_score if assessment is not None else None
    factors: list[str] = []
    explanation = None
    base = None
    final = None
    if assessment is not None:
        base = assessment.base_risk_level
        final = assessment.final_risk_level or incident.current_risk_level
        if assessment.severity is not None and assessment.likelihood is not None:
            factors.append(f"severity {assessment.severity} × likelihood {assessment.likelihood}")
            try:
                computed = calculate_risk(
                    assessment.severity,
                    assessment.likelihood,
                    bool(incident.hazard_currently_active),
                    int(incident.people_exposed or 0),
                    incident.hazard_category or "",
                    bool(incident.injury_occurred),
                )
                score = int(computed.get("score", score or 0))
                explanation = computed.get("explanation")
                base = computed.get("base_level") or base
                final = computed.get("level") or final
                factors.extend(str(item) for item in (computed.get("escalation_reasons") or []))
            except (RiskInputError, TypeError, ValueError):
                explanation = assessment.severity_reason
        for item in assessment.applied_overrides or []:
            if item:
                factors.append(str(item))
        if incident.duplicate_count and incident.duplicate_count >= 3:
            factors.append("repeated reports")
        if not explanation:
            explanation = redact_text(
                " ".join(part for part in (assessment.severity_reason, assessment.likelihood_reason) if part)
            )
    return AuditRiskAnalysis(
        score=score,
        base_risk_level=base,
        final_risk_level=final,
        calculation_factors=factors,
        explanation=explanation,
        rule_validation="Deterministic engine confirmed severity." if assessment is not None else None,
    )


def _guidance(updates: list[IncidentUpdate]) -> list[AuditGuidanceItem]:
    items: list[AuditGuidanceItem] = []
    for update in updates:
        meta = _meta(update)
        kind = (update.update_type or "").lower()
        nested = meta.get("guidance")
        records: list[dict[str, Any]] = []
        if isinstance(nested, list):
            records.extend(item for item in nested if isinstance(item, dict))
        elif kind in _GUIDANCE_TYPES or meta.get("source_id") or meta.get("source_document"):
            records.append(meta)
        for record in records:
            text = record.get("guidance") or record.get("output_text") or record.get("message") or update.message
            items.append(
                AuditGuidanceItem(
                    guidance=redact_text(str(text) if text else None),
                    language=_language_name(_as_str(record.get("language")) or None),
                    timestamp=update.created_at,
                    source=_as_str(record.get("source_document") or record.get("source")),
                    section=_as_str(record.get("section") or record.get("line_reference")),
                    matched_text=redact_text(_as_str(record.get("matched_text") or record.get("source_text"))),
                    line_reference=_as_str(record.get("line_reference") or record.get("section")),
                    rule_id=_as_str(record.get("rule_id") or record.get("source_id")),
                )
            )
    return items


def _coordination(updates: list[IncidentUpdate]) -> list[AuditCoordinationEvent]:
    events: list[AuditCoordinationEvent] = []
    for update in updates:
        kind = (update.update_type or "").lower()
        meta = _meta(update)
        if kind not in _COORD_TYPES and meta.get("source") != "slack":
            continue
        if kind == "slack_coordination_completed" or kind == "incident_assigned":
            label = "Officer notified"
        elif kind == "slack_coordination_failed":
            label = "Officer alert failed"
        elif "escalat" in kind:
            label = "Escalation message"
        else:
            label = kind.replace("_", " ").capitalize()
        channel = _as_str(meta.get("channel")) or (
            "Slack" if meta.get("source") == "slack" or "slack" in kind else None
        )
        events.append(
            AuditCoordinationEvent(
                event=label,
                channel=channel,
                time=update.created_at,
                detail=redact_text(update.message),
            )
        )
    return events


def _assignments(rows: list[Assignment]) -> list[AuditAssignmentChange]:
    ordered = sorted(
        rows,
        key=lambda row: _aware(row.assigned_at or row.created_at) or datetime.min.replace(tzinfo=timezone.utc),
    )
    history: list[AuditAssignmentChange] = []
    previous = None
    for row in ordered:
        history.append(
            AuditAssignmentChange(
                officer=officer_label(row),
                previous_officer=previous,
                assigned_at=row.assigned_at or row.created_at,
                reason=row.assignment_status,
            )
        )
        previous = officer_label(row)
    return history


def _timeline(updates: list[IncidentUpdate]) -> list[AuditTimelineEvent]:
    events: list[AuditTimelineEvent] = []
    for update in updates:
        actor = update.actor_reference or update.actor_type
        events.append(
            AuditTimelineEvent(
                time=update.created_at,
                event=(update.update_type or "update").replace("_", " "),
                update_type=update.update_type,
                message=redact_text(update.message),
                created_by=redact_text(actor) if actor else None,
            )
        )
    return events


def _resolution(
    incident: Incident,
    updates: list[IncidentUpdate],
    evidence: list[IncidentEvidence],
) -> AuditResolution:
    display = to_display_status(incident.status) or incident.status
    resolved_by = None
    message = None
    for update in reversed(updates):
        kind = (update.update_type or "").lower()
        new_status = (update.new_status or "").upper()
        if kind in _RESOLUTION_TYPES and (
            "RESOLVED" in new_status
            or "CLOSED" in new_status
            or kind.startswith("incident_closed")
            or kind.startswith("worker_confirm")
        ):
            resolved_by = update.actor_reference or update.actor_type
            message = redact_text(update.message)
            break
        if kind in {"incident_closed", "incident_resolved", "worker_confirmed", "worker_verification_confirmed"}:
            resolved_by = update.actor_reference or update.actor_type
            message = redact_text(update.message)
            break
    urls: list[str] = []
    for row in evidence:
        ref = row.storage_reference
        if ref and _safe_storage_available(ref):
            urls.append(ref)
    verified = None
    if (incident.status or "").upper() in {"RESOLVED", "CLOSED"}:
        verified = "Worker confirmed" if resolved_by else "Recorded as resolved"
    human = None
    if (incident.status or "").upper() in {"RESOLVED", "CLOSED"}:
        actor = (resolved_by or "").lower()
        if "officer" in actor or "safety" in actor:
            human = "Officer confirmed resolution."
        else:
            human = "Resolution recorded on the incident timeline."
    return AuditResolution(
        status=display,
        resolution_message=message,
        resolved_by=redact_text(resolved_by) if resolved_by else None,
        resolved_timestamp=incident.resolved_at or incident.closed_at,
        evidence=urls,
        verification_status=verified,
        human_verification=human,
    )


def _ledger_slice(ledger_path, incident: Incident) -> tuple[list[str], int, Decimal]:
    if not ledger_path.exists():
        return [], 0, Decimal("0")
    try:
        payload = _read_json(ledger_path)
    except Exception:
        log.warning("spend_ledger unreadable for audit export")
        return [], 0, Decimal("0")
    raw_calls = payload.get("recent_calls") if isinstance(payload.get("recent_calls"), list) else []
    start = _aware(incident.created_at)
    end = _aware(incident.resolved_at or incident.closed_at) or _utcnow()
    idents = {incident.incident_ref, str(incident.id)}
    if incident.session_id:
        idents.add(incident.session_id)
    matched: list[dict[str, Any]] = []
    for row in raw_calls:
        if not isinstance(row, dict):
            continue
        row_ident = _as_str(row.get("incident_id") or row.get("incident_ref") or row.get("session_id"))
        if row_ident and row_ident in idents:
            matched.append(row)
            continue
        stamp = _as_str(row.get("timestamp"))
        if start is None or not stamp:
            continue
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        aware = _aware(parsed)
        if aware is not None and start <= aware <= end:
            matched.append(row)
    if not matched:
        return [], 0, Decimal("0")
    roles: list[str] = []
    cost = Decimal("0")
    for row in matched:
        role = _as_str(row.get("model_role") or row.get("role"))
        if role and role not in roles:
            roles.append(role)
        agent = _as_str(row.get("agent_role")) or _ROLE_AGENT.get(role or "")
        if agent and agent not in roles:
            roles.append(agent)
        cost += _as_decimal(row.get("cost_usd"))
        _ = _as_float(row.get("latency_s"))
    return roles, len(matched), cost


def _audit_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_audit_export(
    *,
    incident: Incident,
    assignments: list[Assignment],
    assessments: list[RiskAssessment],
    evidence: list[IncidentEvidence],
    updates: list[IncidentUpdate],
    ledger_path,
) -> AuditExport:
    origin = extract_qr_origin(incident.original_message_text)
    ordered = _sort_updates(updates)
    assessment = assessments[0] if assessments else None
    original = incident.original_message_text
    translated = incident.hazard_description
    if translated and original and translated.strip() == original.strip():
        translated_text = None
    else:
        translated_text = redact_text(translated)
    channel = _channel_label(incident.source_channel)
    packet = AuditExport(
        incident_information=AuditIncidentInformation(
            incident_id=incident.incident_ref,
            title=incident_title(incident),
            category=incident.hazard_category,
            location=incident.location,
            equipment=origin.get("qr_equipment") or incident.site_id,
            created_at=incident.created_at,
            current_status=to_display_status(incident.status) or incident.status,
            current_risk_level=normalize_risk_level(incident.current_risk_level),
            duplicate_count=incident.duplicate_count or 0,
        ),
        original_report=AuditOriginalReport(
            source=channel,
            message=redact_text(original),
            received_at=incident.created_at,
            worker_identifier=mask_reporter(
                incident.reporter_id, is_anonymous=bool(getattr(incident, "is_anonymous", False))
            ),
            communication_channel=channel,
        ),
        language_processing=AuditLanguageProcessing(
            detected_language=incident.detected_language,
            language=_language_name(incident.detected_language),
            original_text=redact_text(original),
            translated_text=translated_text,
            translation_timestamp=incident.created_at if translated_text else None,
        ),
        extracted_information=_extracted(incident, origin),
        ai_decision=_ai_decision(incident, assessment, ordered),
        risk_analysis=_risk_analysis(incident, assessment),
        guidance_history=_guidance(ordered),
        coordination_history=_coordination(ordered),
        assignment_history=_assignments(assignments),
        incident_timeline=_timeline(ordered),
        resolution=_resolution(incident, ordered, evidence),
        audit_metadata=AuditMetadata(
            export_timestamp=_utcnow(),
            system_version="0.1.0",
            audit_export_version=AUDIT_EXPORT_VERSION,
            compliance=[
                "workplace safety audits",
                "incident investigations",
                "regulatory reviews",
            ],
        ),
    )
    roles, calls, cost = _ledger_slice(ledger_path, incident)
    packet.audit_metadata.models_used = roles
    packet.audit_metadata.ai_calls = calls
    packet.audit_metadata.estimated_cost = f"${cost:.2f}"
    packet.audit_metadata.total_processing_time = format_elapsed(
        incident.created_at, incident.resolved_at or incident.closed_at
    )
    dumped = packet.model_dump(mode="json")
    dumped.get("audit_metadata", {}).pop("audit_hash", None)
    packet.audit_metadata.audit_hash = _audit_hash(dumped)
    return packet
