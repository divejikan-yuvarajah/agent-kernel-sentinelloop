"""Read-only SentinelLoop operations dashboard API.

Mounted on the existing Agent Kernel REST server. GET endpoints only.
Consumes already-persisted incident intelligence; does not import agents
or mutate incidents, evidence, or AI decisions.
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
    AnalyticsSummary,
    AuditExport,
    GuardrailComplianceExport,
    GuardrailConfigView,
    GuardrailDebugEvent,
    GuardrailStatus,
    IncidentDetail,
    IncidentListResponse,
    RecurringResponse,
    ReviewQueueResponse,
    RouterStatus,
    TelegramBotStatus,
)
from dashboard.service import DashboardReadService

log = logging.getLogger("sentinelloop.dashboard.api")

_ANALYTICS_TTL_S = 15.0
_RECURRING_TTL_S = 30.0
_ROUTER_TTL_S = 5.0


class DashboardHandler(RESTRequestHandler):
    """FastAPI router for the command-center dashboard."""

    def __init__(
        self,
        repository: Any | None = None,
        *,
        service: DashboardReadService | None = None,
        ledger_path: Any | None = None,
    ) -> None:
        self._repository = repository
        self._service = service
        self._ledger_path = ledger_path
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
                description="Inbound channel filter: telegram, whatsapp, slack, email.",
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
            "/telegram/health",
            "/router/status",
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
