"""Read-only Pydantic response models for the operations dashboard."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class IncidentSummary(_Out):
    incident_id: str
    title: str | None = None
    category: str | None = None
    location: str | None = None
    status: str
    risk_level: str | None = None
    risk_score: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    elapsed_time: str | None = None
    assigned_officer: str | None = None
    duplicate_count: int = 0
    loop_stage: str | None = None
    source: str | None = None
    location_verified: bool = False
    qr_equipment: str | None = None


class IncidentListResponse(_Out):
    items: list[IncidentSummary]
    total: int
    limit: int
    offset: int
    sort_by: str
    sort_order: str


class ReporterInfo(_Out):
    reporter_id: str
    source_channel: str | None = None
    language: str | None = None


class RiskIntelligence(_Out):
    risk_level: str | None = None
    risk_score: int | None = None
    ai_confidence: float | None = None
    risk_explanation: str | None = None
    detected_hazards: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None


class EvidenceItem(_Out):
    evidence_id: str
    kind: str | None = None
    label: str | None = None
    source: str | None = None
    stage: str | None = None
    uploaded_at: datetime | None = None
    has_image: bool = False
    storage_available: bool = False


class TimelineEvent(_Out):
    timestamp: datetime | None = None
    title: str
    detail: str | None = None
    actor: str | None = None


class LinkedIncident(_Out):
    incident_id: str
    title: str | None = None
    status: str | None = None
    similarity_score: float | None = None
    relationship: Literal["canonical", "duplicate"] = "duplicate"


class DuplicateIntelligence(_Out):
    duplicate_count: int = 0
    linked_incidents: list[LinkedIncident] = Field(default_factory=list)
    duplicate_similarity_score: float | None = None


class IncidentDetail(_Out):
    incident_id: str
    record_id: UUID | None = None
    title: str | None = None
    description: str | None = None
    category: str | None = None
    location: str | None = None
    reporter: ReporterInfo
    created_at: datetime | None = None
    updated_at: datetime | None = None
    status: str
    elapsed_time: str | None = None
    assigned_officer: str | None = None
    loop_stage: str | None = None
    risk: RiskIntelligence
    evidence: list[EvidenceItem] = Field(default_factory=list)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    duplicates: DuplicateIntelligence
    source: str | None = None
    location_verified: bool = False
    qr_equipment: str | None = None
    location_confidence: float | None = None


class LoopStageCount(_Out):
    stage: str
    label: str
    count: int
    percentage: float


class ActivityEvent(_Out):
    timestamp: datetime | None = None
    kind: str
    summary: str
    incident_id: str | None = None


class QrLocationStat(_Out):
    location: str
    equipment: str | None = None
    count: int
    risk_score: float | None = None
    insight: str | None = None


class RepeatedHazardStat(_Out):
    label: str
    location: str | None = None
    count: int
    insight: str | None = None


class AnalyticsSummary(_Out):
    total_incidents: int
    open_incidents: int
    critical_incidents: int
    resolved_today: int
    avg_response_time: str | None = None
    incidents_last_24_hours: int
    incidents_last_7_days: int
    incidents_by_risk_level: dict[str, int]
    incidents_by_category: dict[str, int]
    average_resolution_time: str | None = None
    fastest_response_time: str | None = None
    slowest_response_time: str | None = None
    loop_stages: list[LoopStageCount] = Field(default_factory=list)
    recent_activity: list[ActivityEvent] = Field(default_factory=list)
    qr_tagged_incidents: int = 0
    top_qr_locations: list[QrLocationStat] = Field(default_factory=list)
    most_repeated_hazards: list[RepeatedHazardStat] = Field(default_factory=list)
    repeated_hazard_locations: list[RepeatedHazardStat] = Field(default_factory=list)
    duplicate_detection_stats: dict[str, int] = Field(default_factory=dict)


class RecurringHazard(_Out):
    category: str
    location: str
    count: int
    period: str = "30 days"
    severity: str
    recommendation: str
    recurrence_percentage: float
    trend_direction: Literal["up", "down", "stable"]
    first_seen: datetime | None = None
    last_seen: datetime | None = None


class RecurringResponse(_Out):
    items: list[RecurringHazard]
    window_days: int = 30
    threshold: int = 3


class ModelCallRecord(_Out):
    timestamp: str | None = None
    model: str | None = None
    model_role: str | None = None
    agent_role: str | None = None
    tier: str | None = None
    latency_s: float | None = None
    token_usage: dict[str, Any] = Field(default_factory=dict)
    cost_usd: float = 0.0


class RouterBudget(_Out):
    budget_limit: float | None = None
    spent: float = 0.0
    remaining: float | None = None
    usage_percentage: float | None = None


class RouterStatus(_Out):
    budget: RouterBudget
    recent_calls: list[ModelCallRecord] = Field(default_factory=list)
    request_count: int = 0
    paid_call_count: int = 0
    ledger_available: bool = True


AUDIT_EXPORT_VERSION = "1.0"


class AuditIncidentInformation(_Out):
    incident_id: str
    title: str | None = None
    category: str | None = None
    location: str | None = None
    equipment: str | None = None
    created_at: datetime | None = None
    current_status: str
    current_risk_level: str | None = None
    duplicate_count: int = 0


class AuditOriginalReport(_Out):
    source: str | None = None
    message: str | None = None
    received_at: datetime | None = None
    worker_identifier: str | None = None
    communication_channel: str | None = None


class AuditLanguageProcessing(_Out):
    detected_language: str | None = None
    language: str | None = None
    original_text: str | None = None
    translated_text: str | None = None
    translation_timestamp: datetime | None = None


class ExtractedField(_Out):
    field: str
    value: str | None = None
    confidence: float | None = None


class AuditExtractedInformation(_Out):
    fields: list[ExtractedField] = Field(default_factory=list)


class AuditAiDecision(_Out):
    severity: str | None = None
    likelihood: str | None = None
    confidence: float | None = None
    detected_risks: list[str] = Field(default_factory=list)
    reasoning_summary: str | None = None
    ai_recommendation: str | None = None
    human_final_decision: str | None = None
    override_reason: str | None = None
    explanation_label: str | None = None


class AuditRiskAnalysis(_Out):
    score: int | None = None
    base_risk_level: str | None = None
    final_risk_level: str | None = None
    calculation_factors: list[str] = Field(default_factory=list)
    explanation: str | None = None
    rule_validation: str | None = None


class AuditGuidanceItem(_Out):
    guidance: str | None = None
    language: str | None = None
    timestamp: datetime | None = None
    source: str | None = None
    section: str | None = None
    matched_text: str | None = None
    line_reference: str | None = None
    rule_id: str | None = None


class AuditCoordinationEvent(_Out):
    event: str
    channel: str | None = None
    time: datetime | None = None
    detail: str | None = None


class AuditAssignmentChange(_Out):
    officer: str | None = None
    previous_officer: str | None = None
    assigned_at: datetime | None = None
    reason: str | None = None


class AuditTimelineEvent(_Out):
    time: datetime | None = None
    event: str
    update_type: str | None = None
    message: str | None = None
    created_by: str | None = None


class AuditResolution(_Out):
    status: str | None = None
    resolution_message: str | None = None
    resolved_by: str | None = None
    resolved_timestamp: datetime | None = None
    evidence: list[str] = Field(default_factory=list)
    verification_status: str | None = None
    human_verification: str | None = None


class AuditMetadata(_Out):
    export_timestamp: datetime
    system_version: str
    audit_export_version: str = AUDIT_EXPORT_VERSION
    models_used: list[str] = Field(default_factory=list)
    ai_calls: int = 0
    estimated_cost: str | None = None
    total_processing_time: str | None = None
    audit_hash: str | None = None
    compliance: list[str] = Field(default_factory=list)


class AuditExport(_Out):
    """Inspector-ready explainable-AI packet for one incident. Read-only."""

    incident_information: AuditIncidentInformation
    original_report: AuditOriginalReport
    language_processing: AuditLanguageProcessing
    extracted_information: AuditExtractedInformation
    ai_decision: AuditAiDecision
    risk_analysis: AuditRiskAnalysis
    guidance_history: list[AuditGuidanceItem] = Field(default_factory=list)
    coordination_history: list[AuditCoordinationEvent] = Field(default_factory=list)
    assignment_history: list[AuditAssignmentChange] = Field(default_factory=list)
    incident_timeline: list[AuditTimelineEvent] = Field(default_factory=list)
    resolution: AuditResolution
    audit_metadata: AuditMetadata
