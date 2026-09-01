"""SentinelLoop operations dashboard API.

GET views remain cached reads. Incident creation goes through the shared
intake pipeline via POST /incidents/manual. POST /analytics/predictions/inspect
and POST /handover/generate are the other authorized writes.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from agentkernel.api.handler import RESTRequestHandler
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from dashboard.schemas import (
    AiUsageBreakdown,
    AnalyticsSummary,
    AuditExport,
    EmergencyCommandCenter,
    GuardrailComplianceExport,
    GuardrailConfigView,
    GuardrailDebugEvent,
    GuardrailStatus,
    HandoverAnalyticsOut,
    HandoverGenerateIn,
    HandoverGenerateOut,
    HandoverHistoryOut,
    HandoverRecord,
    IncidentDetail,
    IncidentListResponse,
    InspectionRequestIn,
    InspectionRequestOut,
    ManualIncidentRequest,
    ManualIncidentResponse,
    PredictionsResponse,
    RecurringResponse,
    ReviewQueueResponse,
    RouterStatus,
    SystemHealth,
    TelegramBotStatus,
    VoiceAnalytics,
)
from dashboard.service import DashboardReadService

log = logging.getLogger("sentinelloop.dashboard.api")

_ANALYTICS_TTL_S = 15.0
_RECURRING_TTL_S = 30.0
_ROUTER_TTL_S = 5.0
_PREDICTIONS_TTL_S = 600.0


class DashboardHandler(RESTRequestHandler):
    """FastAPI router for the command-center dashboard."""

    def __init__(
        self,
        repository: Any | None = None,
        *,
        service: DashboardReadService | None = None,
        ledger_path: Any | None = None,
        call_model_fn: Any | None = None,
        coordination_service: Any | None = None,
        orchestrator: Any | None = None,
    ) -> None:
        self._repository = repository
        self._service = service
        self._ledger_path = ledger_path
        self._call_model_fn = call_model_fn
        self._coordination_service = coordination_service
        self._orchestrator = orchestrator
        self._slack = None
        self._cache: dict[str, tuple[float, Any]] = {}

    def _reader(self) -> DashboardReadService:
        if self._service is not None:
            return self._service
        from database.repository import IncidentRepository

        repo = self._repository or IncidentRepository()
        self._service = DashboardReadService(repo, ledger_path=self._ledger_path)
        return self._service

    def _cached(self, key: str, ttl: float, builder):
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        value = builder()
        self._cache[key] = (now, value)
        return value

    async def _cached_async(self, key: str, ttl: float, builder):
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit is not None and now - hit[0] < ttl:
            return hit[1]
        value = builder()
        if hasattr(value, "__await__"):
            value = await value
        self._cache[key] = (now, value)
        return value

    def get_router(self) -> APIRouter:
        router = APIRouter(prefix="/api", tags=["dashboard"])

        @router.get(
            "/incidents",
            response_model=IncidentListResponse,
            summary="List incidents",
            description=(
                "Lightweight incident summaries for command-center monitoring. "
                "Evidence objects are omitted. Read-only."
            ),
            responses={
                500: {
                    "description": "internal dashboard failure",
                    "content": {"application/json": {"example": {"detail": "internal dashboard failure"}}},
                }
            },
        )
        async def list_incidents(
            status: str | None = Query(
                default=None,
                description="Repository or display status (example: OPEN, IN_PROGRESS, Assigned).",
            ),
            risk_level: str | None = Query(
                default=None,
                description="Risk filter (example: CRITICAL, HIGH, MEDIUM, LOW).",
            ),
            stage: str | None = Query(
                default=None,
                description="Loop-ring stage filter: report, understand, assess, alert, act, verify, learn.",
            ),
            source_channel: str | None = Query(
                default=None,
                description="Inbound channel filter: telegram, telegram, slack, email.",
            ),
            language: str | None = Query(
                default=None,
                description="Detected worker language filter: si, ta, en, Sinhala, Tamil, English.",
            ),
            limit: int = Query(default=20, ge=1, le=100, description="Page size."),
            offset: int = Query(default=0, ge=0, description="Number of matching rows to skip."),
            sort_by: str | None = Query(
                default="newest",
                description="newest, oldest, highest_risk, longest_unresolved, created_at, updated_at, risk_score.",
            ),
            sort_order: str | None = Query(default=None, description="asc or desc. Used with column sort_by values."),
        ) -> IncidentListResponse:
            try:
                return await asyncio.to_thread(
                    self._reader().list_incidents,
                    status=status,
                    risk_level=risk_level,
                    stage=stage,
                    source_channel=source_channel,
                    language=language,
                    limit=limit,
                    offset=offset,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard list_incidents failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.post(
            "/incidents/manual",
            response_model=ManualIncidentResponse,
            summary="Log a hazard from the dashboard",
            description="Runs the same intake → incident → risk → guidance → coordination pipeline as Telegram.",
        )
        async def create_manual_incident(body: ManualIncidentRequest) -> ManualIncidentResponse:
            return await self._create_manual_incident(body)

        @router.post(
            "/incidents/simulate",
            response_model=ManualIncidentResponse,
            summary="Simulate an emergency report",
            description="Demo/judge helper. Same pipeline as a worker report, without Telegram credentials.",
        )
        async def simulate_incident(body: ManualIncidentRequest | None = None) -> ManualIncidentResponse:
            payload = body or ManualIncidentRequest()
            payload.simulate = True
            return await self._create_manual_incident(payload)

        @router.get(
            "/system-health",
            response_model=SystemHealth,
            summary="Live command-center health",
            description="Telegram, Slack, database, and AI availability plus last incident timestamp.",
        )
        async def system_health() -> SystemHealth:
            try:
                return await asyncio.to_thread(self._reader().system_health)
            except Exception:
                log.exception("dashboard system_health failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/incidents/{incident_id}",
            response_model=IncidentDetail,
            summary="Incident intelligence",
            description=(
                "Complete incident record for operators: risk, evidence metadata, "
                "chronological timeline, and duplicate links. Accepts incident_ref or UUID."
            ),
            responses={
                404: {
                    "description": "incident not found",
                    "content": {"application/json": {"example": {"detail": "incident not found"}}},
                },
                500: {
                    "description": "internal dashboard failure",
                    "content": {"application/json": {"example": {"detail": "internal dashboard failure"}}},
                },
            },
        )
        async def get_incident(incident_id: str) -> IncidentDetail:
            try:
                detail = await asyncio.to_thread(self._reader().get_incident, incident_id)
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard get_incident failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None
            if detail is None:
                raise HTTPException(status_code=404, detail="incident not found")
            return detail

        @router.get(
            "/incidents/{incident_id}/audit-export",
            response_model=AuditExport,
            summary="Explainable AI audit trail",
            description=(
                "Inspector-ready JSON for one incident: original report, language processing, "
                "AI judgement, deterministic risk rules, guidance sources, human actions, "
                "and resolution evidence. Read-only. Accepts incident_ref or UUID. "
                "Never returns API keys or system prompts."
            ),
            responses={
                404: {
                    "description": "incident not found",
                    "content": {"application/json": {"example": {"detail": "incident not found"}}},
                },
                500: {
                    "description": "internal dashboard failure",
                    "content": {"application/json": {"example": {"detail": "internal dashboard failure"}}},
                },
            },
        )
        async def audit_export(incident_id: str) -> AuditExport:
            try:
                packet = await asyncio.to_thread(self._reader().export_audit, incident_id)
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard audit_export failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None
            if packet is None:
                raise HTTPException(status_code=404, detail="incident not found")
            return packet

        @router.get(
            "/analytics/summary",
            response_model=AnalyticsSummary,
            summary="Operational KPIs",
            description="Aggregated incident counts, response performance, loop-stage mix, and recent activity.",
            responses={
                500: {
                    "description": "internal dashboard failure",
                    "content": {"application/json": {"example": {"detail": "internal dashboard failure"}}},
                }
            },
        )
        async def analytics_summary() -> AnalyticsSummary:
            try:
                return await asyncio.to_thread(
                    self._cached, "analytics.summary", _ANALYTICS_TTL_S, self._reader().analytics_summary
                )
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard analytics_summary failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/analytics/recurring",
            response_model=RecurringResponse,
            summary="Recurring workplace hazards",
            description=(
                "Learn capability: groups incidents by category and location. "
                "Flags 3 or more reports in a 30-day window."
            ),
            responses={
                500: {
                    "description": "internal dashboard failure",
                    "content": {"application/json": {"example": {"detail": "internal dashboard failure"}}},
                }
            },
        )
        async def analytics_recurring() -> RecurringResponse:
            try:
                return await asyncio.to_thread(
                    self._cached, "analytics.recurring", _RECURRING_TTL_S, self._reader().recurring_hazards
                )
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard analytics_recurring failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/analytics/predictions",
            response_model=PredictionsResponse,
            summary="Predicted risk zones",
            description=(
                "Deterministic recurrence patterns plus prevention-agent wording. "
                "Computed from the incidents table. Cached for 10 minutes."
            ),
            responses={
                500: {
                    "description": "internal dashboard failure",
                    "content": {"application/json": {"example": {"detail": "internal dashboard failure"}}},
                }
            },
        )
        async def analytics_predictions() -> PredictionsResponse:
            try:
                from dashboard.predictions import build_predictions

                repo = self._repository or self._reader()._repo
                return await self._cached_async(
                    "analytics.predictions",
                    _PREDICTIONS_TTL_S,
                    lambda: build_predictions(repo, call_model_fn=self._call_model_fn),
                )
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard analytics_predictions failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.post(
            "/analytics/predictions/inspect",
            response_model=InspectionRequestOut,
            summary="Request preventive inspection",
            description="Posts a Slack inspection_request note. Does not create a schedule or mutate incidents.",
        )
        async def request_prediction_inspection(body: InspectionRequestIn) -> InspectionRequestOut:
            try:
                from agents.coordination_agent import request_inspection
                from dashboard.predictions import record_inspection_triggered

                result = await request_inspection(
                    {
                        "location": body.location,
                        "category": body.category,
                        "reason": body.reason,
                        "recommendation": body.recommendation,
                    },
                    service=self._coordination_service,
                )
                if result.posted:
                    record_inspection_triggered()
                    self._cache.pop("analytics.predictions", None)
                return InspectionRequestOut(
                    posted=result.posted,
                    message_type=result.message_type or "inspection_request",
                    location=result.location or body.location,
                    coordination_error=result.coordination_error,
                    slack_channel_id=result.slack_channel_id,
                )
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard request_inspection failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/emergencies",
            response_model=EmergencyCommandCenter,
            summary="Emergency Command Center",
            description="Read-only active emergencies, response metrics, timeline, and history.",
        )
        async def emergencies() -> EmergencyCommandCenter:
            try:
                return await asyncio.to_thread(self._reader().emergency_command_center)
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard emergencies failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.post(
            "/handover/generate",
            response_model=HandoverGenerateOut,
            summary="Generate shift handover",
            description="Manual demo trigger. Collects incident facts, calls role_fast once, stores the briefing, and posts to Slack Safety Channel.",
        )
        async def generate_handover(body: HandoverGenerateIn) -> HandoverGenerateOut:
            try:
                from agents.handover_agent import generate_handover_summary
                from integrations.slack_handler import SlackHandler

                repo = self._repository or self._reader()._repo
                slack = self._slack
                if slack is None:
                    slack = getattr(self._coordination_service, "slack", None) or SlackHandler()
                record = await generate_handover_summary(
                    body.shift_label,
                    repository=repo,
                    call_model_fn=self._call_model_fn,
                    slack=slack,
                    generated_by="dashboard_officer",
                )
                self._cache.pop("handover.latest", None)
                self._cache.pop("handover.history", None)
                self._cache.pop("handover.analytics", None)
                return HandoverGenerateOut(success=True, handover=HandoverRecord.model_validate(record))
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard handover_generate failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/handover/latest",
            response_model=HandoverRecord | None,
            summary="Latest shift handover",
        )
        async def latest_handover() -> HandoverRecord | None:
            try:
                from agents.handover_agent import get_latest_handover

                repo = self._repository or self._reader()._repo
                record = get_latest_handover(repo)
                return HandoverRecord.model_validate(record) if record else None
            except Exception:
                log.exception("dashboard handover_latest failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/handover/history",
            response_model=HandoverHistoryOut,
            summary="Shift handover history",
        )
        async def handover_history() -> HandoverHistoryOut:
            try:
                from agents.handover_agent import _public_record, list_stored_handovers

                repo = self._repository or self._reader()._repo
                rows = [_public_record(item) for item in list_stored_handovers(repo)]
                return HandoverHistoryOut(items=[HandoverRecord.model_validate(item) for item in rows], total=len(rows))
            except Exception:
                log.exception("dashboard handover_history failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/handover/analytics",
            response_model=HandoverAnalyticsOut,
            summary="Handover analytics",
        )
        async def handover_analytics() -> HandoverAnalyticsOut:
            try:
                from agents.handover_agent import handover_analytics as build_analytics

                repo = self._repository or self._reader()._repo
                return HandoverAnalyticsOut.model_validate(build_analytics(repo))
            except Exception:
                log.exception("dashboard handover_analytics failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/handover/compare",
            summary="Compare morning and evening shifts",
        )
        async def handover_compare() -> dict[str, Any]:
            try:
                from agents.handover_agent import handover_analytics as build_analytics

                repo = self._repository or self._reader()._repo
                return build_analytics(repo).get("compare") or {}
            except Exception:
                log.exception("dashboard handover_compare failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/handover/{handover_id}/export.json",
            summary="Export handover JSON",
        )
        async def handover_export_json(handover_id: str) -> dict[str, Any]:
            try:
                from agents.handover_agent import _public_record, list_stored_handovers

                repo = self._repository or self._reader()._repo
                for item in list_stored_handovers(repo):
                    public = _public_record(item)
                    if str(public.get("handover_id")) == str(handover_id):
                        return public
                raise HTTPException(status_code=404, detail="handover not found")
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard handover_export_json failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/handover/{handover_id}/export.pdf",
            summary="Export handover PDF",
        )
        async def handover_export_pdf(handover_id: str):
            try:
                from fastapi.responses import Response

                from agents.handover_agent import _public_record, handover_pdf_bytes, list_stored_handovers

                repo = self._repository or self._reader()._repo
                for item in list_stored_handovers(repo):
                    public = _public_record(item)
                    if str(public.get("handover_id")) == str(handover_id):
                        return Response(
                            content=handover_pdf_bytes(public),
                            media_type="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="handover-{handover_id}.pdf"'},
                        )
                raise HTTPException(status_code=404, detail="handover not found")
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard handover_export_pdf failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/telegram/health",
            response_model=TelegramBotStatus,
            summary="Telegram bot monitoring",
            description="Read-only Telegram transport health: polling, last message, errors, and volume.",
        )
        async def telegram_health() -> TelegramBotStatus:
            try:
                return await asyncio.to_thread(self._reader().telegram_status)
            except Exception:
                log.exception("dashboard telegram_health failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/router/status",
            response_model=RouterStatus,
            summary="AI model router transparency",
            description=(
                "Read-only view of spend_ledger.json: recent model calls, "
                "OPENROUTER_BUDGET_CEILING_USD, and remaining budget. Never returns API keys."
            ),
            responses={
                500: {
                    "description": "internal dashboard failure",
                    "content": {"application/json": {"example": {"detail": "internal dashboard failure"}}},
                }
            },
        )
        async def router_status(
            limit: int = Query(default=8, ge=1, le=40, description="Number of recent model calls to include."),
        ) -> RouterStatus:
            try:
                return await asyncio.to_thread(
                    self._cached,
                    f"router.status.{limit}",
                    _ROUTER_TTL_S,
                    lambda: self._reader().router_status(last_n=limit),
                )
            except HTTPException:
                raise
            except Exception:
                log.exception("dashboard router_status failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/ai-usage",
            response_model=AiUsageBreakdown,
            summary="AI Usage Dashboard",
            description="Text, vision, and voice spend against OPENROUTER_BUDGET_CEILING_USD. Never returns API keys.",
        )
        async def ai_usage() -> AiUsageBreakdown:
            try:
                return await asyncio.to_thread(
                    self._cached,
                    "ai.usage",
                    _ROUTER_TTL_S,
                    lambda: self._reader().ai_usage(),
                )
            except Exception:
                log.exception("dashboard ai_usage failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/analytics/voice",
            response_model=VoiceAnalytics,
            summary="Voice safety report analytics",
            description="Voice volume, languages, incident sources, and completion rates. Read-only.",
        )
        async def voice_analytics() -> VoiceAnalytics:
            try:
                summary = await asyncio.to_thread(
                    self._cached,
                    "analytics.summary",
                    _ANALYTICS_TTL_S,
                    self._reader().analytics_summary,
                )
                return summary.voice_analytics
            except Exception:
                log.exception("dashboard voice_analytics failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/guardrails/status",
            response_model=GuardrailStatus,
            summary="AI Safety Center",
            description="Active guardrails, metrics, violations, and compliance charts. Read-only.",
        )
        async def guardrail_status() -> GuardrailStatus:
            try:
                return await asyncio.to_thread(self._reader().guardrail_status)
            except Exception:
                log.exception("dashboard guardrail_status failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/guardrails/review-queue",
            response_model=ReviewQueueResponse,
            summary="Human review queue",
            description="High and Critical incidents waiting for Slack Closed. Dashboard actions are display-only.",
        )
        async def review_queue() -> ReviewQueueResponse:
            try:
                return await asyncio.to_thread(self._reader().review_queue)
            except Exception:
                log.exception("dashboard review_queue failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/guardrails/debug",
            response_model=list[GuardrailDebugEvent],
            summary="Guardrail debug console",
            description="Admin-only operator view of validation events. Never exposed to workers.",
        )
        async def guardrail_debug(
            limit: int = Query(default=100, ge=1, le=500),
        ) -> list[GuardrailDebugEvent]:
            try:
                return await asyncio.to_thread(self._reader().guardrail_debug, limit=limit)
            except Exception:
                log.exception("dashboard guardrail_debug failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/guardrails/config",
            response_model=GuardrailConfigView,
            summary="Guardrail configuration",
            description="Read-only policy display. Normal users cannot modify safety rules.",
        )
        async def guardrail_config() -> GuardrailConfigView:
            try:
                return await asyncio.to_thread(self._reader().guardrail_config)
            except Exception:
                log.exception("dashboard guardrail_config failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        @router.get(
            "/guardrails/compliance-export",
            response_model=GuardrailComplianceExport,
            summary="Export safety compliance report",
            description="Validation history, violations, human approvals, and audit timestamps. Read-only JSON.",
        )
        async def guardrail_compliance_export() -> GuardrailComplianceExport:
            try:
                return await asyncio.to_thread(self._reader().guardrail_compliance_export)
            except Exception:
                log.exception("dashboard compliance_export failed")
                raise HTTPException(status_code=500, detail="internal dashboard failure") from None

        async def writes_forbidden() -> JSONResponse:
            return JSONResponse(status_code=405, content={"detail": "dashboard is read-only"})

        for path in (
            "/incidents",
            "/incidents/{incident_id}",
            "/incidents/{incident_id}/audit-export",
            "/analytics/summary",
            "/analytics/recurring",
            "/analytics/predictions",
            "/emergencies",
            "/handover/latest",
            "/handover/history",
            "/handover/analytics",
            "/handover/compare",
            "/telegram/health",
            "/system-health",
            "/router/status",
            "/ai-usage",
            "/analytics/voice",
            "/guardrails/status",
            "/guardrails/review-queue",
            "/guardrails/debug",
            "/guardrails/config",
            "/guardrails/compliance-export",
        ):
            router.add_api_route(
                path,
                writes_forbidden,
                methods=["POST", "PUT", "PATCH", "DELETE"],
                include_in_schema=False,
            )

        return router

    async def _create_manual_incident(self, body: ManualIncidentRequest) -> ManualIncidentResponse:
        from services.demo_mode import demo_mode_enabled
        from services.demo_pipeline import build_demo_orchestrator
        from services.incident_intake_service import (
            compose_manual_report_text,
            decode_photo,
            process_incident_input,
            validate_manual_incident,
        )

        scenarios = {
            "electrical": {
                "description": "Electrical panel sparking near the isolator. Three workers nearby.",
                "category": "Electrical",
                "location": "Electrical Room",
                "people_exposed": 3,
                "is_active": True,
                "injury_reported": False,
            },
            "chemical": {
                "description": "Chemical smell and a small leak at the storage cabinet.",
                "category": "Chemical",
                "location": "Chemical Storage",
                "people_exposed": 2,
                "is_active": True,
                "injury_reported": False,
            },
            "machine": {
                "description": "Guard missing on machine 4. Belt is still running.",
                "category": "Machine",
                "location": "CNC Area",
                "people_exposed": 4,
                "is_active": True,
                "injury_reported": False,
            },
            "smoke": {
                "description": "There is smoke coming from machine 4. Three workers are nearby.",
                "category": "Fire/Smoke",
                "location": "Machine 4",
                "people_exposed": 3,
                "is_active": True,
                "injury_reported": False,
            },
        }
        data = body
        if body.simulate:
            sample = scenarios.get((body.scenario or "smoke").strip().lower(), scenarios["smoke"])
            data = ManualIncidentRequest.model_validate({**sample, "created_by": body.created_by or "demo_officer"})

        error = validate_manual_incident(
            description=data.description,
            category=data.category,
            location=data.location,
            people_exposed=data.people_exposed,
            photo_filename=data.photo_filename,
            photo_content_type=data.photo_content_type,
            is_active=data.is_active,
            injury_reported=data.injury_reported,
        )
        if error:
            raise HTTPException(status_code=400, detail=error)

        people = int(data.people_exposed or 0)
        reporter = (data.reporter_name or data.created_by or "").strip() or None
        equipment = (data.equipment_involved or "").strip() or None
        raw_text = compose_manual_report_text(
            data.description,
            category=data.category,
            location=data.location,
            people_exposed=people,
            is_active=bool(data.is_active),
            injury_reported=bool(data.injury_reported),
            equipment_involved=equipment,
        )
        photo = decode_photo(
            data.photo_base64,
            filename=data.photo_filename,
            content_type=data.photo_content_type,
        )
        orch = self._orchestrator
        if orch is None and (demo_mode_enabled() or body.simulate):
            orch = build_demo_orchestrator(
                repository=self._repository or self._reader()._repo,
                raw_text=raw_text,
                category=data.category,
                location=data.location,
                people_exposed=people,
                is_active=bool(data.is_active),
                already_injured=bool(data.injury_reported),
            )
        try:
            result = await process_incident_input(
                source="manual",
                raw_text=raw_text,
                metadata={
                    "created_by": reporter,
                    "reporter_name": reporter,
                    "category": data.category,
                    "location": data.location,
                    "people_exposed": people,
                    "is_active": data.is_active,
                    "injury_reported": data.injury_reported,
                    "equipment_involved": equipment,
                    "photo": photo,
                },
                orchestrator=orch,
            )
        except HTTPException:
            raise
        except Exception:
            log.exception("dashboard manual incident failed")
            raise HTTPException(status_code=500, detail="internal dashboard failure") from None
        self._cache.clear()
        return ManualIncidentResponse(
            incident_id=result.incident_id or result.canonical_incident_id,
            status=result.status,
            risk_level=result.risk_level,
            risk_score=result.risk_score,
            risk_explanation=result.risk_explanation,
            guidance_text=result.guidance_text,
            pipeline=list(result.pipeline_trace or []),
            slack_alert_sent=bool(result.slack_alert_sent or result.coordination_completed),
            input_channel="manual",
            input_method="dashboard",
            error=result.error,
        )
