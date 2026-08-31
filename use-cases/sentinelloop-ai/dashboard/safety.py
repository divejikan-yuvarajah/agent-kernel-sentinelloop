"""Read-only safety-center views. Does not import agents or mutate incidents."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dashboard.schemas import (
    GuardrailComplianceExport,
    GuardrailConfigView,
    GuardrailDebugEvent,
    GuardrailMetrics,
    GuardrailStatus,
    GuardrailTimelineEvent,
    GuidanceVerification,
    IncidentSafetyPanel,
    ReviewQueueItem,
    ReviewQueueResponse,
    SafetyActiveCard,
    SafetyComplianceCharts,
    SafetyViolationCounts,
)
from guardrails.config import load_guardrail_config
from guardrails.events import list_guardrail_events
from guardrails.output_validation import sanitize_analytics_record
from tools.lifecycle import STATUS_CLOSED, to_display_status


def _risk_key(value: str | None) -> str:
    return (value or "").strip().upper()


def safety_status_for_incident(
    *,
    risk_level: str | None,
    status: str | None,
    events: list[Any] | None = None,
) -> str:
    display = (to_display_status(status) or status or "").replace("_", " ")
    blocked = any(not getattr(item, "approved", True) for item in events or [])
    if blocked:
        return "Guardrail Blocked"
    if _risk_key(risk_level) in {"HIGH", "CRITICAL"} and display != STATUS_CLOSED:
        return "Human Review Required"
    return "Validated"


def build_safety_panel(
    *,
    incident_id: str,
    risk_level: str | None,
    status: str | None,
    assigned_officer: str | None,
    events: list[Any] | None = None,
    guidance: dict[str, Any] | None = None,
) -> IncidentSafetyPanel:
    status_label = safety_status_for_incident(risk_level=risk_level, status=status, events=events)
    human = _risk_key(risk_level) in {"HIGH", "CRITICAL"}
    display = to_display_status(status) or status or ""
    closed = display == STATUS_CLOSED
    guidance = guidance or {}
    kb_file = guidance.get("knowledge_base_file")
    matched = guidance.get("matched_line_count")
    total = guidance.get("guidance_count") or matched
    hallucination = guidance.get("hallucination_check") or ("Passed" if status_label == "Validated" else "Pending")
    closure = (
        "Closed by authorized officer"
        if closed
        else ("Blocked until officer approval" if human else "Auto-close allowed for Low/Medium")
    )
    timeline = [
        GuardrailTimelineEvent(
            timestamp=getattr(item, "timestamp", None),
            title=getattr(item, "event", "guardrail"),
            detail=getattr(item, "decision", None) or getattr(item, "rule", None),
        )
        for item in (events or [])[-12:]
    ]
    if not timeline:
        timeline = [
            GuardrailTimelineEvent(title="Report received", detail="Awaiting validation events"),
        ]
    return IncidentSafetyPanel(
        incident_id=incident_id,
        safety_status=status_label,
        risk_level=risk_level,
        human_review="Required" if human and not closed else "Not required",
        guidance="Knowledge Base Verified" if hallucination in {"Passed", "Fallback"} else "Pending",
        closure=closure,
        auto_close_disabled=human and not closed,
        guidance_verification=GuidanceVerification(
            knowledge_base_file=kb_file,
            supported_lines=f"{matched}/{total}" if matched is not None and total is not None else None,
            hallucination_check=hallucination,
            generated_guidance=guidance.get("generated_guidance"),
        ),
        timeline=timeline,
        assigned_reviewer=assigned_officer,
    )


def build_guardrail_status(
    *,
    incidents: list[Any],
    budget_limit: float | None,
    spent: float,
    anonymous_count: int,
) -> GuardrailStatus:
    from guardrails.events import guardrail_metrics

    metrics = guardrail_metrics()
    total = len(incidents)
    human = 0
    blocked = 0
    anonymous = anonymous_count
    for item in incidents:
        risk = getattr(item, "current_risk_level", None) or getattr(item, "risk_level", None)
        status = getattr(item, "status", None)
        label = safety_status_for_incident(risk_level=risk, status=status)
        if label == "Human Review Required":
            human += 1
        if label == "Guardrail Blocked":
            blocked += 1
    charts = SafetyComplianceCharts(
        guidance_validation_success_rate=_rate(metrics["passed"], metrics["total_validations"]),
        incidents_requiring_human_review=human,
        blocked_ai_outputs=metrics["blocked"],
        anonymous_reports_percentage=_rate(anonymous, total),
        average_ai_cost_per_incident=round(spent / total, 4) if total else 0.0,
    )
    return GuardrailStatus(
        cards=[
            SafetyActiveCard(
                name="Guidance Grounding", active=True, spec_rule="AI-generated safety instructions must be grounded"
            ),
            SafetyActiveCard(
                name="Human Review Protection", active=True, spec_rule="Human intervention for Critical incidents"
            ),
            SafetyActiveCard(
                name="Privacy Protection", active=True, spec_rule="Do not unnecessarily expose worker contact data"
            ),
            SafetyActiveCard(
                name="Budget Control",
                active=True,
                spec_rule="Paid OpenRouter spend is governed by OPENROUTER_BUDGET_CEILING_USD",
            ),
        ],
        metrics=GuardrailMetrics(
            total_validations=metrics["total_validations"],
            passed=metrics["passed"],
            blocked=metrics["blocked"],
            warnings=metrics["warnings"],
        ),
        violations=SafetyViolationCounts(
            guidance_hallucinations=metrics["guidance_hallucinations"],
            privacy_attempts=metrics["privacy_attempts"],
            blocked_closures=metrics["blocked_closures"],
            budget_blocks=metrics["budget_blocks"],
        ),
        charts=charts,
        budget_ceiling_usd=budget_limit,
        budget_spent_usd=spent,
    )


def build_review_queue(incidents: list[Any], assignments: dict[Any, Any]) -> ReviewQueueResponse:
    items: list[ReviewQueueItem] = []
    now = datetime.now(timezone.utc)
    for incident in incidents:
        risk = getattr(incident, "current_risk_level", None)
        status = to_display_status(getattr(incident, "status", None)) or getattr(incident, "status", "")
        if _risk_key(risk) not in {"HIGH", "CRITICAL"}:
            continue
        if status == STATUS_CLOSED:
            continue
        created = getattr(incident, "created_at", None)
        waiting = None
        if isinstance(created, datetime):
            delta = now - (created if created.tzinfo else created.replace(tzinfo=timezone.utc))
            waiting = f"{int(delta.total_seconds() // 60)}m"
        assignment = assignments.get(getattr(incident, "id", None))
        reviewer = None
        if assignment is not None:
            reviewer = getattr(assignment, "assigned_to", None) or getattr(assignment, "team", None)
        items.append(
            ReviewQueueItem(
                incident_id=getattr(incident, "incident_ref", None) or str(getattr(incident, "id", "")),
                risk_level=risk,
                reason="Human approval required according to SPEC.md",
                assigned_reviewer=reviewer,
                waiting_time=waiting,
                status=status,
                actions=["Approve Closure", "Reject", "Request More Info"],
                actions_enabled=False,
                action_hint="Closure is performed with the Slack Closed button. This dashboard is read-only.",
            )
        )
    return ReviewQueueResponse(items=items, total=len(items))


def build_debug_events(limit: int = 100) -> list[GuardrailDebugEvent]:
    events = list_guardrail_events(limit=limit)
    out: list[GuardrailDebugEvent] = []
    for item in events:
        out.append(
            GuardrailDebugEvent(
                timestamp=item.timestamp,
                guardrail=item.guardrail,
                event=item.event,
                input_summary=str((item.metadata or {}).get("length") or item.agent or ""),
                validation_result="passed" if item.approved else "blocked",
                agent_output=item.decision,
                rule_violated=item.rule if not item.approved else None,
                decision=item.decision,
                incident_id=item.incident_id,
                violations=item.violations,
            )
        )
    return out


def build_config_view() -> GuardrailConfigView:
    cfg = load_guardrail_config()
    import os

    ceiling = os.environ.get("OPENROUTER_BUDGET_CEILING_USD")
    return GuardrailConfigView(
        ai_budget_ceiling=ceiling,
        guidance_validation_strictness=str(cfg.get("guidance_validation_strictness")),
        anonymous_data_policy=str(cfg.get("anonymous_data_policy")),
        closure_rules=str(cfg.get("closure_rules")),
        max_text_length=int(cfg["max_text_length"]),
        max_attachment_bytes=int(cfg["max_attachment_bytes"]),
        writable=False,
    )


def build_compliance_export(
    *, incidents: list[Any], spent: float, budget_limit: float | None
) -> GuardrailComplianceExport:
    from guardrails.events import guardrail_metrics

    events = [item.model_dump() for item in list_guardrail_events(limit=500)]
    safe_events = [sanitize_analytics_record(dict(item), is_anonymous=True) for item in events]
    metrics = guardrail_metrics()
    return GuardrailComplianceExport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        validation_history=safe_events,
        violations=SafetyViolationCounts(
            guidance_hallucinations=metrics["guidance_hallucinations"],
            privacy_attempts=metrics["privacy_attempts"],
            blocked_closures=metrics["blocked_closures"],
            budget_blocks=metrics["budget_blocks"],
        ),
        human_approvals=sum(
            1 for item in incidents if (to_display_status(getattr(item, "status", None)) == STATUS_CLOSED)
        ),
        incident_count=len(incidents),
        ai_spend_usd=spent,
        budget_ceiling_usd=budget_limit,
        audit_note="AI does not control safety-critical outcomes without validation.",
    )


def _rate(part: int, whole: int) -> float:
    if not whole:
        return 0.0
    return round(100.0 * part / whole, 2)


def guidance_from_updates(updates: list[Any]) -> dict[str, Any]:
    for update in reversed(updates or []):
        meta = getattr(update, "metadata", None) or {}
        if not isinstance(meta, dict):
            continue
        if meta.get("knowledge_base_file") or meta.get("hallucination_check"):
            return dict(meta)
        if getattr(update, "update_type", None) in {"guidance_generated", "guidance_fallback"}:
            return dict(meta)
    return {}
