"""Assemble read-only dashboard views from the existing repository.

Does not import agents, compute risk, or mutate incidents.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from dashboard.schemas import (
    ActivityEvent,
    AnalyticsSummary,
    DuplicateIntelligence,
    EvidenceItem,
    IncidentDetail,
    IncidentListResponse,
    IncidentSummary,
    LinkedIncident,
    LoopStageCount,
    ModelCallRecord,
    QrLocationStat,
    RecurringHazard,
    RecurringResponse,
    RepeatedHazardStat,
    ReporterInfo,
    RiskIntelligence,
    RouterBudget,
    RouterStatus,
    TimelineEvent,
)
from database.models import Assignment, Incident, IncidentEvidence, IncidentUpdate, RiskAssessment
from database.repository import IncidentRepository
from database.schemas import IncidentFilters
from tools.duplicate_tools import duplicate_detection_stats
from tools.lifecycle import to_display_status
from tools.qr_tags import SOURCE_QR_TAGGED, extract_qr_origin

log = logging.getLogger("sentinelloop.dashboard")

CLOSED_STATUSES = frozenset({"RESOLVED", "CLOSED"})
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
_SECRET_URL_RE = re.compile(r"(access_token|authorization|api[_-]?key)=", re.IGNORECASE)

LOOP_STAGES: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("report", "Report", frozenset({"REPORTED", "NEW"})),
    ("understand", "Understand", frozenset({"ASSESSING", "VALIDATING"})),
    ("assess", "Assess", frozenset({"OPEN", "ASSESSED"})),
    ("alert", "Alert", frozenset({"ASSIGNED", "ACCEPTED"})),
    ("act", "Act", frozenset({"IN_PROGRESS"})),
    ("verify", "Verify", frozenset({"AWAITING_VERIFICATION"})),
    ("learn", "Learn", frozenset({"RESOLVED", "CLOSED"})),
)

_STAGE_STATUSES = {key: statuses for key, _label, statuses in LOOP_STAGES}
_STATUS_TO_STAGE = {status: key for key, _label, statuses in LOOP_STAGES for status in statuses}

_RISK_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
_RISK_SCORE_FALLBACK = {"LOW": 4, "MEDIUM": 9, "HIGH": 12, "CRITICAL": 16}
_ROLE_TIER = {"role_fast": "FAST MODEL", "role_reasoning": "SMART MODEL", "role_guidance": "GUIDANCE MODEL"}
_ROLE_AGENT = {"role_fast": "intake_agent", "role_reasoning": "risk_agent", "role_guidance": "guidance_agent"}

_TIMELINE_TITLES = {
    "incident_draft_started": "Report received",
    "incident_created": "Report received",
    "evidence_added": "Evidence attached",
    "status_transition": "Status updated",
    "slack_coordination_completed": "Officer assigned",
    "incident_assigned": "Officer assigned",
    "guidance_send_failed": "Worker guidance delayed",
    "slack_coordination_failed": "Coordination failed",
    "duplicate_report_linked": "AI merged reports",
    "duplicate_threshold_reached": "Priority increased",
}

_ACTIVITY_KINDS = {
    "incident_draft_started": "New report",
    "incident_created": "New report",
    "evidence_added": "Evidence",
    "status_transition": "Status",
    "slack_coordination_completed": "Officer action",
    "incident_assigned": "Officer action",
    "duplicate_report_linked": "Duplicate report",
    "duplicate_threshold_reached": "Priority increase",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def redact_text(value: str | None) -> str | None:
    if not value:
        return value
    return _PHONE_RE.sub("[redacted]", value)


def mask_reporter(reporter_id: str, *, is_anonymous: bool = False) -> str:
    if is_anonymous:
        return "anonymous"
    raw = (reporter_id or "").strip()
    if len(raw) <= 4:
        return "••••"
    return f"{raw[:2]}••••{raw[-2:]}"


def normalize_risk_level(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().upper()
    if key in _RISK_RANK:
        return key
    return value.strip() or None


def normalize_status_filter(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    raw = value.strip()
    upper = raw.upper().replace(" ", "_")
    aliases = {
        "NEW": "REPORTED",
        "VALIDATING": "ASSESSING",
        "ASSESSED": "OPEN",
        "ACCEPTED": "ASSIGNED",
    }
    if upper in aliases:
        return aliases[upper]
    display_to_repo = {
        "NEW": "REPORTED",
        "VALIDATING": "ASSESSING",
        "ASSESSED": "OPEN",
        "ASSIGNED": "ASSIGNED",
        "IN PROGRESS": "IN_PROGRESS",
        "AWAITING VERIFICATION": "AWAITING_VERIFICATION",
        "RESOLVED": "RESOLVED",
        "CLOSED": "CLOSED",
    }
    if raw in display_to_repo:
        return display_to_repo[raw]
    return upper


def normalize_risk_filter(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    key = value.strip().upper()
    titled = {"LOW": "Low", "MEDIUM": "Medium", "HIGH": "High", "CRITICAL": "Critical"}
    return titled.get(key, value.strip())


def loop_stage_for_status(status: str | None) -> str:
    repo = (status or "").upper().replace(" ", "_")
    if repo in _STATUS_TO_STAGE:
        return _STATUS_TO_STAGE[repo]
    display = to_display_status(status) or ""
    mapped = display.upper().replace(" ", "_")
    aliases = {
        "NEW": "report",
        "VALIDATING": "understand",
        "ASSESSED": "assess",
        "ASSIGNED": "alert",
        "ACCEPTED": "alert",
        "IN_PROGRESS": "act",
        "AWAITING_VERIFICATION": "verify",
        "RESOLVED": "learn",
        "CLOSED": "learn",
    }
    return aliases.get(mapped, "report")


def statuses_for_stage(stage: str | None) -> frozenset[str] | None:
    if not stage:
        return None
    return _STAGE_STATUSES.get(stage.strip().lower())


def format_elapsed(created: datetime | None, ended: datetime | None = None) -> str | None:
    start = _aware(created)
    if start is None:
        return None
    stop = _aware(ended) or _utcnow()
    seconds = max(0, int((stop - start).total_seconds()))
    return format_duration(seconds)


def format_duration(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def incident_title(incident: Incident) -> str:
    description = (incident.hazard_description or "").strip()
    if description:
        return redact_text(description.splitlines()[0][:160]) or "Untitled incident"
    category = incident.hazard_category or "Hazard"
    location = incident.location or "unspecified location"
    return f"{category} — {location}"


def officer_label(assignment: Assignment | None) -> str | None:
    if assignment is None:
        return None
    name = (assignment.assigned_to or "").strip()
    team = (assignment.team or "").strip()
    if name and team:
        return f"{name} · {team}"
    return name or team or None


def _latest_by_incident(rows: Iterable[Assignment | RiskAssessment]) -> dict[UUID, Any]:
    latest: dict[UUID, Any] = {}
    for row in rows:
        current = latest.get(row.incident_id)
        if current is None:
            latest[row.incident_id] = row
            continue
        current_ts = _aware(getattr(current, "created_at", None)) or datetime.min.replace(tzinfo=timezone.utc)
        row_ts = _aware(getattr(row, "created_at", None)) or datetime.min.replace(tzinfo=timezone.utc)
        if row_ts >= current_ts:
            latest[row.incident_id] = row
    return latest


def _risk_score(incident: Incident, assessment: RiskAssessment | None) -> int | None:
    if assessment is not None and assessment.risk_score is not None:
        return assessment.risk_score
    level = normalize_risk_level(incident.current_risk_level)
    return _RISK_SCORE_FALLBACK.get(level or "")


def _is_open(incident: Incident) -> bool:
    return (incident.status or "").upper() not in CLOSED_STATUSES


def _is_critical(incident: Incident) -> bool:
    return normalize_risk_level(incident.current_risk_level) == "CRITICAL"


def _parse_sort(sort_by: str | None, sort_order: str | None) -> tuple[str, str]:
    raw = (sort_by or "newest").strip().lower().replace("-", "_").replace(" ", "_")
    order = (sort_order or "desc").strip().lower()
    aliases = {
        "newest": ("created_at", "desc"),
        "oldest": ("created_at", "asc"),
        "highest_risk": ("risk_score", "desc"),
        "highest": ("risk_score", "desc"),
        "risk": ("risk_score", "desc"),
        "longest_unresolved": ("unresolved", "asc"),
        "longest": ("unresolved", "asc"),
        "created_at": ("created_at", order if order in {"asc", "desc"} else "desc"),
        "updated_at": ("updated_at", order if order in {"asc", "desc"} else "desc"),
        "risk_score": ("risk_score", order if order in {"asc", "desc"} else "desc"),
        "risk_level": ("risk_score", order if order in {"asc", "desc"} else "desc"),
    }
    if raw in aliases:
        return aliases[raw]
    return "created_at", "desc"


def _sort_key(summary: IncidentSummary, sort_by: str):
    if sort_by == "risk_score":
        return _RISK_RANK.get(normalize_risk_level(summary.risk_level) or "", 0), summary.risk_score or 0
    if sort_by == "updated_at":
        return _aware(summary.updated_at) or datetime.min.replace(tzinfo=timezone.utc)
    if sort_by == "unresolved":
        open_rank = 0 if (summary.status or "").upper() not in CLOSED_STATUSES else 1
        created = _aware(summary.created_at) or datetime.max.replace(tzinfo=timezone.utc)
        return open_rank, created
    return _aware(summary.created_at) or datetime.min.replace(tzinfo=timezone.utc)


def _safe_storage_available(reference: str | None) -> bool:
    if not reference:
        return False
    if _SECRET_URL_RE.search(reference):
        return False
    lower = reference.lower()
    if "graph.facebook.com" in lower or "whatsapp" in lower:
        return False
    return True


class DashboardReadService:
    def __init__(self, repository: IncidentRepository, *, ledger_path: Path | None = None) -> None:
        self._repo = repository
        root = Path(__file__).resolve().parents[1]
        self._ledger_path = ledger_path or (root / ".runtime" / "spend_ledger.json")

    def list_incidents(
        self,
        *,
        status: str | None = None,
        risk_level: str | None = None,
        stage: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> IncidentListResponse:
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)
        sort_key, order = _parse_sort(sort_by, sort_order)
        filters = IncidentFilters(
            status=normalize_status_filter(status),
            current_risk_level=normalize_risk_filter(risk_level),
        )
        incidents = self._repo.list_all_incidents(filters)
        stage_statuses = statuses_for_stage(stage)
        if stage_statuses is not None:
            incidents = [item for item in incidents if (item.status or "").upper() in stage_statuses]
        keys = [self._repo.row_key(item) for item in incidents]
        assignments = _latest_by_incident(self._repo.list_assignments_for_incidents(keys))
        risks = _latest_by_incident(self._repo.list_risk_assessments_for_incidents(keys))
        summaries = [self._to_summary(item, assignments.get(item.id), risks.get(item.id)) for item in incidents]
        reverse = order == "desc"
        summaries.sort(key=lambda row: _sort_key(row, sort_key), reverse=reverse)
        page = summaries[offset : offset + limit]
        return IncidentListResponse(
            items=page,
            total=len(summaries),
            limit=limit,
            offset=offset,
            sort_by=sort_key,
            sort_order=order,
        )

    def get_incident(self, incident_id: str) -> IncidentDetail | None:
        incident = self._resolve_incident(incident_id)
        if incident is None:
            return None
        key = self._repo.row_key(incident)
        assignment = self._repo.get_assignment_for_incident(key)
        assessments = self._repo.list_risk_assessments_for_incident(key)
        assessment = assessments[0] if assessments else None
        evidence = self._repo.list_evidence_for_incident(key)
        updates = self._repo.list_updates_for_incident(key)
        linked: list[LinkedIncident] = []
        similarity: float | None = None
        if incident.duplicate_of is not None:
            canonical = self._repo.get_incident(incident.duplicate_of)
            if canonical is not None:
                linked.append(
                    LinkedIncident(
                        incident_id=canonical.incident_ref,
                        title=incident_title(canonical),
                        status=to_display_status(canonical.status) or canonical.status,
                        relationship="canonical",
                    )
                )
        for sibling in self._repo.list_duplicates_of(incident.id):
            linked.append(
                LinkedIncident(
                    incident_id=sibling.incident_ref,
                    title=incident_title(sibling),
                    status=to_display_status(sibling.status) or sibling.status,
                    relationship="duplicate",
                )
            )
        for update in updates:
            meta = update.metadata or {}
            score = meta.get("similarity") or meta.get("duplicate_similarity_score")
            if isinstance(score, (int, float)):
                similarity = float(score)
        origin = extract_qr_origin(incident.original_message_text)
        from dashboard.safety import build_safety_panel, guidance_from_updates, safety_status_for_incident
        from guardrails.events import list_guardrail_events

        events = list_guardrail_events(incident_id=incident.incident_ref)
        if not events:
            events = list_guardrail_events(incident_id=str(incident.id))
        status_label = safety_status_for_incident(
            risk_level=incident.current_risk_level,
            status=incident.status,
            events=events,
        )
        return IncidentDetail(
            incident_id=incident.incident_ref,
            record_id=incident.id,
            title=incident_title(incident),
            description=redact_text(incident.hazard_description or incident.original_message_text),
            category=incident.hazard_category,
            location=incident.location,
            reporter=ReporterInfo(
                reporter_id=mask_reporter(
                    incident.reporter_id, is_anonymous=bool(getattr(incident, "is_anonymous", False))
                ),
                source_channel=incident.source_channel,
                language=incident.detected_language,
            ),
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            status=to_display_status(incident.status) or incident.status,
            elapsed_time=format_elapsed(incident.created_at, incident.resolved_at if not _is_open(incident) else None),
            assigned_officer=officer_label(assignment),
            loop_stage=loop_stage_for_status(incident.status),
            risk=self._risk_intelligence(incident, assessment),
            evidence=[self._to_evidence(row) for row in evidence],
            timeline=self._timeline(incident, assignment, assessment, updates),
            duplicates=DuplicateIntelligence(
                duplicate_count=incident.duplicate_count or 0,
                linked_incidents=linked,
                duplicate_similarity_score=similarity,
            ),
            source=SOURCE_QR_TAGGED if origin["location_verified"] else origin["source"],
            location_verified=bool(origin["location_verified"]),
            qr_equipment=origin["qr_equipment"],
            location_confidence=1.0 if origin["location_verified"] else None,
            is_anonymous=bool(getattr(incident, "is_anonymous", False)),
            safety_status=status_label,
            safety=build_safety_panel(
                incident_id=incident.incident_ref,
                risk_level=incident.current_risk_level,
                status=incident.status,
                assigned_officer=officer_label(assignment),
                events=events,
                guidance=guidance_from_updates(updates),
            ),
        )

    def export_audit(self, incident_id: str):
        """Inspector packet for one incident. None when the incident does not exist."""
        from dashboard.audit import build_audit_export

        incident = self._resolve_incident(incident_id)
        if incident is None:
            return None
        key = self._repo.row_key(incident)
        return build_audit_export(
            incident=incident,
            assignments=self._repo.list_assignments_for_incidents([key]),
            assessments=self._repo.list_risk_assessments_for_incident(key),
            evidence=self._repo.list_evidence_for_incident(key),
            updates=self._repo.list_updates_for_incident(key),
            ledger_path=self._ledger_path,
        )

    def analytics_summary(self) -> AnalyticsSummary:
        incidents = self._repo.list_all_incidents()
        assignments = _latest_by_incident(
            self._repo.list_assignments_for_incidents([self._repo.row_key(item) for item in incidents])
        )
        now = _utcnow()
        day_ago = now - timedelta(hours=24)
        week_ago = now - timedelta(days=7)
        today = now.date()
        by_risk = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        by_category: dict[str, int] = {}
        stage_counts = {key: 0 for key, _label, _statuses in LOOP_STAGES}
        open_n = 0
        critical_n = 0
        resolved_today = 0
        last_24 = 0
        last_7 = 0
        response_seconds: list[float] = []
        resolution_seconds: list[float] = []
        for incident in incidents:
            created = _aware(incident.created_at)
            if created is not None and created >= day_ago:
                last_24 += 1
            if created is not None and created >= week_ago:
                last_7 += 1
            if _is_open(incident):
                open_n += 1
            if _is_critical(incident):
                critical_n += 1
            resolved_at = _aware(incident.resolved_at)
            if resolved_at is not None and resolved_at.date() == today:
                resolved_today += 1
            level = normalize_risk_level(incident.current_risk_level) or "MEDIUM"
            by_risk[level] = by_risk.get(level, 0) + 1
            category = incident.hazard_category or "Uncategorized"
            by_category[category] = by_category.get(category, 0) + 1
            stage_counts[loop_stage_for_status(incident.status)] = (
                stage_counts.get(loop_stage_for_status(incident.status), 0) + 1
            )
            assignment = assignments.get(incident.id)
            assigned_at = _aware(assignment.assigned_at) if assignment is not None else None
            if created is not None and assigned_at is not None and assigned_at >= created:
                response_seconds.append((assigned_at - created).total_seconds())
            if created is not None and resolved_at is not None and resolved_at >= created:
                resolution_seconds.append((resolved_at - created).total_seconds())
        total = len(incidents)
        loop_stages = []
        for key, label, _statuses in LOOP_STAGES:
            count = stage_counts.get(key, 0)
            loop_stages.append(
                LoopStageCount(
                    stage=key,
                    label=label,
                    count=count,
                    percentage=round((count / total) * 100, 1) if total else 0.0,
                )
            )
        updates = self._repo.list_recent_updates(limit=12)
        refs = {item.id: item.incident_ref for item in incidents}
        activity = [
            ActivityEvent(
                timestamp=row.created_at,
                kind=_ACTIVITY_KINDS.get(row.update_type, "System event"),
                summary=redact_text(row.message) or _timeline_title(row),
                incident_id=refs.get(row.incident_id),
            )
            for row in updates
        ]
        qr_stats = _qr_location_stats(incidents)
        repeat_stats = _repeated_hazard_stats(incidents)
        return AnalyticsSummary(
            total_incidents=total,
            open_incidents=open_n,
            critical_incidents=critical_n,
            resolved_today=resolved_today,
            avg_response_time=format_duration(_mean(response_seconds)),
            incidents_last_24_hours=last_24,
            incidents_last_7_days=last_7,
            incidents_by_risk_level=by_risk,
            incidents_by_category=by_category,
            average_resolution_time=format_duration(_mean(resolution_seconds)),
            fastest_response_time=format_duration(min(response_seconds) if response_seconds else None),
            slowest_response_time=format_duration(max(response_seconds) if response_seconds else None),
            loop_stages=loop_stages,
            recent_activity=activity,
            qr_tagged_incidents=qr_stats["tagged"],
            top_qr_locations=qr_stats["top"],
            most_repeated_hazards=repeat_stats["hazards"],
            repeated_hazard_locations=repeat_stats["locations"],
            duplicate_detection_stats=duplicate_detection_stats(),
        )

    def recurring_hazards(self, *, window_days: int = 30, threshold: int = 3) -> RecurringResponse:
        incidents = self._repo.list_all_incidents()
        now = _utcnow()
        start = now - timedelta(days=window_days)
        in_window = [item for item in incidents if (_aware(item.created_at) or now) >= start]
        groups: dict[tuple[str, str], list[Incident]] = {}
        for incident in in_window:
            key = (incident.hazard_category or "Uncategorized", incident.location or "Unknown location")
            groups.setdefault(key, []).append(incident)
        window_total = len(in_window) or 1
        items: list[RecurringHazard] = []
        midpoint = start + timedelta(days=window_days / 2)
        for (category, location), rows in groups.items():
            if len(rows) < threshold:
                continue
            ranked = sorted(
                rows,
                key=lambda row: _RISK_RANK.get(normalize_risk_level(row.current_risk_level) or "", 0),
            )
            top_level = normalize_risk_level(ranked[-1].current_risk_level) or "MEDIUM"
            first = min((_aware(row.created_at) or now for row in rows))
            last = max((_aware(row.created_at) or now for row in rows))
            first_half = sum(1 for row in rows if (_aware(row.created_at) or now) < midpoint)
            second_half = len(rows) - first_half
            if second_half > first_half:
                trend: str = "up"
            elif second_half < first_half:
                trend = "down"
            else:
                trend = "stable"
            recommendation = (
                "Requires preventive action" if top_level in {"HIGH", "CRITICAL"} else "Monitor for recurrence"
            )
            items.append(
                RecurringHazard(
                    category=category,
                    location=location,
                    count=len(rows),
                    period=f"{window_days} days",
                    severity=top_level,
                    recommendation=recommendation,
                    recurrence_percentage=round((len(rows) / window_total) * 100, 1),
                    trend_direction=trend,  # type: ignore[arg-type]
                    first_seen=first,
                    last_seen=last,
                )
            )
        items.sort(key=lambda row: (-row.count, row.category, row.location))
        return RecurringResponse(items=items, window_days=window_days, threshold=threshold)

    def router_status(self, *, last_n: int = 8) -> RouterStatus:
        last_n = min(max(last_n, 1), 40)
        ceiling = _decimal_env("OPENROUTER_BUDGET_CEILING_USD")
        if not self._ledger_path.exists():
            return RouterStatus(
                budget=_budget(ceiling, Decimal("0")),
                recent_calls=[],
                ledger_available=False,
            )
        try:
            payload = _read_json(self._ledger_path)
        except Exception:
            log.warning("spend_ledger unreadable")
            return RouterStatus(budget=_budget(ceiling, Decimal("0")), ledger_available=False)
        spent = _as_decimal(payload.get("cumulative_spend_usd"))
        raw_calls = payload.get("recent_calls") if isinstance(payload.get("recent_calls"), list) else []
        calls: list[ModelCallRecord] = []
        for row in raw_calls[-last_n:][::-1]:
            if not isinstance(row, dict):
                continue
            role = str(row.get("model_role") or row.get("role") or "")
            usage = row.get("token_usage") if isinstance(row.get("token_usage"), dict) else {}
            calls.append(
                ModelCallRecord(
                    timestamp=_as_str(row.get("timestamp")),
                    model=_as_str(row.get("model")),
                    model_role=_ROLE_TIER.get(role, role or None),
                    agent_role=_as_str(row.get("agent_role")) or _ROLE_AGENT.get(role),
                    tier=_as_str(row.get("tier")),
                    latency_s=_as_float(row.get("latency_s")),
                    token_usage={
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                    },
                    cost_usd=float(_as_decimal(row.get("cost_usd"))),
                )
            )
        return RouterStatus(
            budget=_budget(ceiling, spent),
            recent_calls=calls,
            request_count=int(payload.get("request_count") or 0),
            paid_call_count=int(payload.get("paid_call_count") or 0),
            ledger_available=True,
        )

    def _spend_snapshot(self) -> tuple[float, float | None]:
        status = self.router_status()
        spent = float(status.budget.spent or 0)
        limit = status.budget.budget_limit
        return spent, limit

    def guardrail_status(self):
        from dashboard.safety import build_guardrail_status

        incidents = self._repo.list_all_incidents(IncidentFilters())
        spent, limit = self._spend_snapshot()
        anonymous = sum(1 for item in incidents if getattr(item, "is_anonymous", False))
        return build_guardrail_status(incidents=incidents, budget_limit=limit, spent=spent, anonymous_count=anonymous)

    def review_queue(self):
        from dashboard.safety import build_review_queue

        incidents = self._repo.list_all_incidents(IncidentFilters())
        keys = [self._repo.row_key(item) for item in incidents]
        assignments = _latest_by_incident(self._repo.list_assignments_for_incidents(keys))
        return build_review_queue(incidents, assignments)

    def guardrail_debug(self, *, limit: int = 100):
        from dashboard.safety import build_debug_events

        return build_debug_events(limit=limit)

    def guardrail_config(self):
        from dashboard.safety import build_config_view

        return build_config_view()

    def guardrail_compliance_export(self):
        from dashboard.safety import build_compliance_export

        incidents = self._repo.list_all_incidents(IncidentFilters())
        spent, limit = self._spend_snapshot()
        return build_compliance_export(incidents=incidents, spent=spent, budget_limit=limit)

    def _resolve_incident(self, incident_id: str) -> Incident | None:
        raw = incident_id.strip()
        try:
            uuid = UUID(raw)
        except ValueError:
            uuid = None
        if uuid is not None:
            found = self._repo.get_incident(uuid)
            if found is not None:
                return found
        return self._repo.get_incident_by_ref(raw)

    def _to_summary(
        self,
        incident: Incident,
        assignment: Assignment | None,
        assessment: RiskAssessment | None,
    ) -> IncidentSummary:
        ended = None if _is_open(incident) else incident.resolved_at or incident.closed_at
        origin = extract_qr_origin(incident.original_message_text)
        from dashboard.safety import safety_status_for_incident

        return IncidentSummary(
            incident_id=incident.incident_ref,
            title=incident_title(incident),
            category=incident.hazard_category,
            location=incident.location,
            status=to_display_status(incident.status) or incident.status,
            risk_level=normalize_risk_level(incident.current_risk_level),
            risk_score=_risk_score(incident, assessment),
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            elapsed_time=format_elapsed(incident.created_at, ended),
            assigned_officer=officer_label(assignment),
            duplicate_count=incident.duplicate_count or 0,
            loop_stage=loop_stage_for_status(incident.status),
            source=SOURCE_QR_TAGGED if origin["location_verified"] else origin["source"],
            location_verified=bool(origin["location_verified"]),
            qr_equipment=origin["qr_equipment"],
            safety_status=safety_status_for_incident(risk_level=incident.current_risk_level, status=incident.status),
            is_anonymous=bool(getattr(incident, "is_anonymous", False)),
        )

    def _risk_intelligence(self, incident: Incident, assessment: RiskAssessment | None) -> RiskIntelligence:
        hazards: list[str] = []
        if incident.hazard_category:
            hazards.append(incident.hazard_category)
        if incident.hazard_currently_active:
            hazards.append("Hazard currently active")
        if incident.injury_occurred:
            hazards.append("Injury reported")
        if incident.people_exposed:
            hazards.append(f"People exposed: {incident.people_exposed}")
        if assessment is not None:
            for item in assessment.applied_overrides or []:
                if item and item not in hazards:
                    hazards.append(str(item))
        explanation = None
        reasoning = None
        confidence = None
        score = _risk_score(incident, assessment)
        if assessment is not None:
            explanation = redact_text(assessment.severity_reason)
            reasoning = redact_text(
                " ".join(part for part in (assessment.severity_reason, assessment.likelihood_reason) if part)
            )
            if assessment.severity is not None and assessment.likelihood is not None:
                confidence = round(min(0.99, (assessment.severity + assessment.likelihood) / 10), 2)
        return RiskIntelligence(
            risk_level=normalize_risk_level(
                (assessment.final_risk_level if assessment is not None else None) or incident.current_risk_level
            ),
            risk_score=score,
            ai_confidence=confidence,
            risk_explanation=explanation,
            detected_hazards=hazards,
            reasoning_summary=reasoning,
        )

    def _to_evidence(self, row: IncidentEvidence) -> EvidenceItem:
        kind = (row.evidence_type or "").lower()
        is_image = kind.startswith("image") or kind in {"photo", "jpeg", "png", "webp"}
        return EvidenceItem(
            evidence_id=str(row.id),
            kind=row.evidence_type,
            label=redact_text(row.caption_or_description) or (row.stage or "evidence"),
            source=row.source,
            stage=row.stage,
            uploaded_at=row.created_at,
            has_image=is_image,
            storage_available=_safe_storage_available(row.storage_reference),
        )

    def _timeline(
        self,
        incident: Incident,
        assignment: Assignment | None,
        assessment: RiskAssessment | None,
        updates: list[IncidentUpdate],
    ) -> list[TimelineEvent]:
        events: list[TimelineEvent] = []
        if incident.created_at is not None:
            events.append(
                TimelineEvent(
                    timestamp=incident.created_at,
                    title="Report received",
                    detail=incident.source_channel,
                    actor="worker",
                )
            )
        if assessment is not None:
            events.append(
                TimelineEvent(
                    timestamp=assessment.created_at,
                    title="Risk assessment generated",
                    detail=assessment.final_risk_level or incident.current_risk_level,
                    actor="risk_agent",
                )
            )
        if assignment is not None and assignment.assigned_at is not None:
            events.append(
                TimelineEvent(
                    timestamp=assignment.assigned_at,
                    title="Officer assigned",
                    detail=officer_label(assignment),
                    actor="coordination_agent",
                )
            )
        for update in updates:
            events.append(
                TimelineEvent(
                    timestamp=update.created_at,
                    title=_timeline_title(update),
                    detail=redact_text(update.message) or _status_detail(update),
                    actor=update.actor_type,
                )
            )
        if incident.resolved_at is not None:
            events.append(
                TimelineEvent(
                    timestamp=incident.resolved_at,
                    title="Incident resolved",
                    actor="followup_agent",
                )
            )
        events.sort(key=lambda item: _aware(item.timestamp) or datetime.min.replace(tzinfo=timezone.utc))
        deduped: list[TimelineEvent] = []
        seen: set[tuple[str, str | None]] = set()
        for event in events:
            stamp = (_aware(event.timestamp).isoformat() if _aware(event.timestamp) else "", event.title)
            if stamp in seen:
                continue
            seen.add(stamp)
            deduped.append(event)
        return deduped


def _timeline_title(update: IncidentUpdate) -> str:
    if update.update_type in _TIMELINE_TITLES:
        return _TIMELINE_TITLES[update.update_type]
    if update.update_type == "status_transition" and update.new_status:
        display = to_display_status(update.new_status) or update.new_status
        mapping = {
            "Validating": "AI classification completed",
            "Assessed": "Risk assessment generated",
            "Assigned": "Officer assigned",
            "In Progress": "Investigation started",
            "Awaiting Verification": "Awaiting verification",
            "Resolved": "Incident resolved",
            "Closed": "Incident closed",
        }
        return mapping.get(display, f"Status: {display}")
    return update.update_type.replace("_", " ").capitalize()


def _status_detail(update: IncidentUpdate) -> str | None:
    if update.previous_status and update.new_status:
        previous = to_display_status(update.previous_status) or update.previous_status
        nxt = to_display_status(update.new_status) or update.new_status
        return f"{previous} → {nxt}"
    return None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _decimal_env(name: str) -> Decimal | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None


def _as_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _repeated_hazard_stats(incidents: list[Incident]) -> dict[str, list[RepeatedHazardStat]]:
    hazard_buckets: dict[tuple[str, str], int] = {}
    location_buckets: dict[str, int] = {}
    for incident in incidents:
        reports = int(incident.duplicate_count or 0)
        if reports <= 1:
            continue
        location = incident.location or "Unknown location"
        category = incident.hazard_category or "hazard"
        hazard_buckets[(category, location)] = hazard_buckets.get((category, location), 0) + reports
        location_buckets[location] = location_buckets.get(location, 0) + reports
    hazards = [
        RepeatedHazardStat(
            label=f"{category} · {location}",
            location=location,
            count=count,
            insight="This equipment has recurring reports. Consider inspection." if count >= 3 else None,
        )
        for (category, location), count in hazard_buckets.items()
    ]
    hazards.sort(key=lambda row: (-row.count, row.label))
    locations = [
        RepeatedHazardStat(label=location, location=location, count=count, insight=None)
        for location, count in location_buckets.items()
    ]
    locations.sort(key=lambda row: (-row.count, row.label or ""))
    return {"hazards": hazards[:8], "locations": locations[:8]}


def _qr_location_stats(incidents: list[Incident]) -> dict[str, Any]:
    now = _utcnow()
    month_start = now - timedelta(days=30)
    buckets: dict[tuple[str, str], list[Incident]] = {}
    tagged = 0
    for incident in incidents:
        origin = extract_qr_origin(incident.original_message_text)
        if not origin["location_verified"]:
            continue
        tagged += 1
        location = str(origin["qr_location"] or incident.location or "Unknown location")
        equipment = str(origin["qr_equipment"] or "")
        buckets.setdefault((location, equipment), []).append(incident)
    top: list[QrLocationStat] = []
    for (location, equipment), rows in buckets.items():
        ranks = [_RISK_RANK.get(normalize_risk_level(row.current_risk_level) or "", 2) for row in rows]
        avg = sum(ranks) / len(ranks) if ranks else 0
        month_rows = [row for row in rows if (_aware(row.created_at) or now) >= month_start]
        categories: dict[str, int] = {}
        for row in month_rows:
            key = row.hazard_category or "hazard"
            categories[key] = categories.get(key, 0) + 1
        insight = None
        if categories:
            top_cat, top_n = max(categories.items(), key=lambda item: item[1])
            label = equipment or location
            if top_n >= 3:
                insight = f"{label} has {top_n} {top_cat} reports this month. Recommend maintenance inspection."
        top.append(
            QrLocationStat(
                location=location,
                equipment=equipment or None,
                count=len(rows),
                risk_score=round(avg * 4, 1),
                insight=insight,
            )
        )
    top.sort(key=lambda row: (-row.count, row.location))
    return {"tagged": tagged, "top": top[:8]}


def _budget(ceiling: Decimal | None, spent: Decimal) -> RouterBudget:
    if ceiling is None:
        return RouterBudget(budget_limit=None, spent=float(spent), remaining=None, usage_percentage=None)
    remaining = ceiling - spent
    if remaining < 0:
        remaining = Decimal("0")
    pct = float((spent / ceiling) * 100) if ceiling > 0 else 0.0
    return RouterBudget(
        budget_limit=float(ceiling),
        spent=float(spent),
        remaining=float(remaining),
        usage_percentage=round(pct, 1),
    )


def _read_json(path: Path) -> dict[str, Any]:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ledger is not an object")
    return payload
