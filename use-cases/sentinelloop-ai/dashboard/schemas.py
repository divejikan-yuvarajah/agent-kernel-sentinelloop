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
    safety_status: str | None = None
    is_anonymous: bool = False
    input_channel: str | None = None
    assigned_team: str | None = None
    reporter_name: str | None = None


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
    uploaded_by: str | None = None
    content_kind: str | None = None


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


class VoiceReport(_Out):
    duration_seconds: float | None = None
    language: str | None = None
    transcript: str | None = None
    audio_format: str | None = "ogg"


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
    is_anonymous: bool = False
    safety_status: str | None = None
    safety: IncidentSafetyPanel | None = None
    input_channel: str | None = None
    voice_report: VoiceReport | None = None


class ChannelShare(_Out):
    channel: str
    count: int
    percentage: float


class TelegramBotStatus(_Out):
    connected: bool = False
    polling_active: bool = False
    last_message_at: datetime | None = None
    last_message: str | None = None
    errors: int = 0
    messages_today: int = 0
    active_sessions: int = 0
    voice_reports: int = 0
    image_reports: int = 0
    emergency_reports: int = 0
    text_reports: int = 0
    message_types: dict[str, float] = Field(default_factory=dict)
    language_distribution: dict[str, float] = Field(default_factory=dict)


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
    reports_by_channel: list[ChannelShare] = Field(default_factory=list)
    telegram_message_types: dict[str, float] = Field(default_factory=dict)
    telegram_languages: dict[str, float] = Field(default_factory=dict)


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


class PredictionItem(_Out):
    location: str
    category: str
    reason: str
    recommendation: str
    trend: str
    incident_count: int = 0
    frequency_score: float = 0.0
    risk_level: str | None = None
    reason_factors: list[str] = Field(default_factory=list)
    weekly_counts: list[int] = Field(default_factory=list)
    generated_by: str = "prevention_agent"
    confidence: float | None = None
    prediction_id: str | None = None
    location_hotspot: bool = False
    days_since_last: int = 0
    span_days: int = 0
    timeline: list[dict[str, str]] = Field(default_factory=list)


class HeatmapCell(_Out):
    location: str
    risk: str
    marker: str
    active: int = 0
    predicted: bool = False


class PreventionAnalytics(_Out):
    predicted_risk_zones: int = 0
    resolved_future_risks: int = 0
    inspections_triggered: int = 0
    prevented_recurrences: int = 0


class PredictionsResponse(_Out):
    generated_at: datetime
    last_updated: datetime
    prediction_count: int
    predictions: list[PredictionItem] = Field(default_factory=list)
    heatmap: list[HeatmapCell] = Field(default_factory=list)
    analytics: PreventionAnalytics = Field(default_factory=PreventionAnalytics)
    weekly_counts: list[int] = Field(default_factory=list)


class InspectionRequestIn(_Out):
    location: str
    category: str | None = None
    reason: str | None = None
    recommendation: str | None = None


class InspectionRequestOut(_Out):
    posted: bool
    message_type: str = "inspection_request"
    location: str | None = None
    coordination_error: str | None = None
    slack_channel_id: str | None = None


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


class SafetyActiveCard(_Out):
    name: str
    active: bool = True
    spec_rule: str | None = None


class GuardrailMetrics(_Out):
    total_validations: int = 0
    passed: int = 0
    blocked: int = 0
    warnings: int = 0


class SafetyViolationCounts(_Out):
    guidance_hallucinations: int = 0
    privacy_attempts: int = 0
    blocked_closures: int = 0
    budget_blocks: int = 0


class SafetyComplianceCharts(_Out):
    guidance_validation_success_rate: float = 0.0
    incidents_requiring_human_review: int = 0
    blocked_ai_outputs: int = 0
    anonymous_reports_percentage: float = 0.0
    average_ai_cost_per_incident: float = 0.0


class GuardrailStatus(_Out):
    cards: list[SafetyActiveCard] = Field(default_factory=list)
    metrics: GuardrailMetrics = Field(default_factory=GuardrailMetrics)
    violations: SafetyViolationCounts = Field(default_factory=SafetyViolationCounts)
    charts: SafetyComplianceCharts = Field(default_factory=SafetyComplianceCharts)
    budget_ceiling_usd: float | None = None
    budget_spent_usd: float = 0.0


class GuardrailTimelineEvent(_Out):
    timestamp: str | None = None
    title: str
    detail: str | None = None


class GuidanceVerification(_Out):
    knowledge_base_file: str | None = None
    supported_lines: str | None = None
    hallucination_check: str | None = None
    generated_guidance: str | None = None


class IncidentSafetyPanel(_Out):
    incident_id: str
    safety_status: str
    risk_level: str | None = None
    human_review: str
    guidance: str
    closure: str
    auto_close_disabled: bool = False
    guidance_verification: GuidanceVerification = Field(default_factory=GuidanceVerification)
    timeline: list[GuardrailTimelineEvent] = Field(default_factory=list)
    assigned_reviewer: str | None = None


class ReviewQueueItem(_Out):
    incident_id: str
    risk_level: str | None = None
    reason: str
    assigned_reviewer: str | None = None
    waiting_time: str | None = None
    status: str | None = None
    actions: list[str] = Field(default_factory=list)
    actions_enabled: bool = False
    action_hint: str | None = None


class ReviewQueueResponse(_Out):
    items: list[ReviewQueueItem] = Field(default_factory=list)
    total: int = 0


class GuardrailDebugEvent(_Out):
    timestamp: str | None = None
    guardrail: str
    event: str
    input_summary: str | None = None
    validation_result: str
    agent_output: str | None = None
    rule_violated: str | None = None
    decision: str | None = None
    incident_id: str | None = None
    violations: list[str] = Field(default_factory=list)


class GuardrailConfigView(_Out):
    ai_budget_ceiling: str | None = None
    guidance_validation_strictness: str | None = None
    anonymous_data_policy: str | None = None
    closure_rules: str | None = None
    max_text_length: int | None = None
    max_attachment_bytes: int | None = None
    writable: bool = False


class GuardrailComplianceExport(_Out):
    generated_at: str
    validation_history: list[dict[str, Any]] = Field(default_factory=list)
    violations: SafetyViolationCounts = Field(default_factory=SafetyViolationCounts)
    human_approvals: int = 0
    incident_count: int = 0
    ai_spend_usd: float = 0.0
    budget_ceiling_usd: float | None = None
    audit_note: str | None = None


IncidentDetail.model_rebuild()
