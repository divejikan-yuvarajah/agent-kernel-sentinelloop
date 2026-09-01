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
    language_name: str | None = None
    transcript: str | None = None
    audio_format: str | None = "ogg"
    input_method: str = "voice"
    audio_used: bool = True
    transcription_cost: float | None = None
    transcription_confidence: float | None = None
    confidence_label: str | None = None
    processing_status: str = "Completed"
    playback_url: str | None = None
    uploaded_by: str = "Worker"
    source: str | None = None
    voice_reply_sent: bool | None = None
    voice_language: str | None = None
    voice_model: str | None = None
    voice_cost_usd: float | None = None
    voice_loop_status: str | None = None
    guidance_playback_url: str | None = None


class AccessibilityResponse(_Out):
    """Full voice safety loop status for incident detail."""

    voice_received: bool = False
    guidance_generated: bool = False
    voice_reply_delivered: bool = False
    text_only: bool = True
    language: str | None = None
    language_name: str | None = None
    status: str = "Text-only response"
    voice_model: str | None = None
    voice_cost_usd: float | None = None
    guidance_playback_url: str | None = None
    loop_steps: list[str] = Field(default_factory=list)


class VisionInsight(_Out):
    hazard_category: str | None = None
    confidence: float | None = None
    observations: list[str] = Field(default_factory=list)
    model_used: str | None = None
    timestamp: str | None = None
    suggestion_only: bool = True
    final_category: str | None = None
    vision_override: bool = False
    override_reason: str | None = None
    changed_by: str | None = None
    confidence_band: str | None = None


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
    input_method: str | None = None
    voice_report: VoiceReport | None = None
    accessibility: AccessibilityResponse | None = None
    vision: VisionInsight | None = None
    included_in_handovers: list["HandoverMention"] = Field(default_factory=list)
    created_by: str | None = None
    pipeline_version: str | None = None
    pipeline_stages: list["PipelineStage"] = Field(default_factory=list)
    people_exposed: int | None = None
    hazard_active: bool | None = None
    injury: bool | None = None
    equipment: str | None = None
    original_text: str | None = None
    translated_text: str | None = None
    language: str | None = None
    assigned_team: str | None = None


class ChannelShare(_Out):
    channel: str
    count: int
    percentage: float


class PipelineStage(_Out):
    name: str
    completed: bool = False
    detail: str | None = None


class ManualIncidentRequest(_Out):
    description: str = ""
    category: str = ""
    location: str = ""
    equipment_involved: str | None = None
    people_exposed: int | None = None
    is_active: bool = True
    injury_reported: bool = False
    photo_base64: str | None = None
    photo_filename: str | None = None
    photo_content_type: str | None = None
    reporter_name: str | None = None
    created_by: str | None = None
    simulate: bool = False
    scenario: str | None = None


class ManualIncidentResponse(_Out):
    incident_id: str | None = None
    status: str | None = None
    risk_level: str | None = None
    risk_score: int | None = None
    risk_explanation: str | None = None
    guidance_text: str | None = None
    pipeline: list[str] = Field(default_factory=list)
    slack_alert_sent: bool = False
    input_channel: str = "manual"
    input_method: str = "dashboard"
    error: str | None = None


class SandboxMessageRequest(_Out):
    session_id: str = ""
    text: str = ""
    image_base64: str | None = None
    image_filename: str | None = None
    image_content_type: str | None = None
    voice_base64: str | None = None
    voice_filename: str | None = None
    voice_content_type: str | None = None
    voice_sample: bool = False
    judge_mode: bool = False
    scenario: str | None = None
    simulate: bool = True


class SandboxMessageResponse(_Out):
    incident_id: str | None = None
    session_id: str | None = None
    language: str | None = None
    translation: str | None = None
    category: str | None = None
    location: str | None = None
    risk_score: int | None = None
    risk_level: str | None = None
    guidance: list[str] = Field(default_factory=list)
    guidance_text: str | None = None
    slack_alert_preview: str | None = None
    slack_preview: str | None = None
    input_channel: str = "sandbox"
    is_sandbox: bool = True
    pipeline: list[str] = Field(default_factory=list)
    pipeline_stages: list[dict[str, Any]] = Field(default_factory=list)
    clarification_required: bool = False
    worker_reply: str | None = None
    vision_suggestion: dict[str, Any] | None = None
    explainability: dict[str, Any] | None = None
    processing_ms: int | None = None
    judge: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    voice_loop: dict[str, Any] | None = None
    error: str | None = None


class SystemHealth(_Out):
    telegram: str = "disconnected"
    slack: str = "disconnected"
    database: str = "disconnected"
    ai_services: str = "unavailable"
    last_incident: datetime | None = None
    last_incident_label: str | None = None
    demo_mode: bool = False


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


class VisionCategoryShare(_Out):
    label: str
    percent: float
    count: int = 0


class VisionLocationHeatmap(_Out):
    location: str
    risk: str | None = None
    electrical_images: int = 0
    machine_images: int = 0
    chemical_images: int = 0
    other_images: int = 0
    total_images: int = 0


class VisionAnalytics(_Out):
    images_analyzed: int = 0
    high_confidence_detections: int = 0
    human_overrides: int = 0
    average_confidence: float = 0.0
    confidence_distribution: dict[str, float] = Field(default_factory=dict)
    hazard_detection_by_image: list[VisionCategoryShare] = Field(default_factory=list)
    model_usage: dict[str, float] = Field(default_factory=dict)
    location_heatmap: list[VisionLocationHeatmap] = Field(default_factory=list)


class VoiceAnalytics(_Out):
    reports_today: int = 0
    average_transcription_seconds: float | None = None
    most_used_language: str | None = None
    languages: dict[str, float] = Field(default_factory=dict)
    incident_sources: dict[str, float] = Field(default_factory=dict)
    completion_rate_voice: float | None = None
    completion_rate_text: float | None = None
    voice_reports_received: int = 0
    voice_replies_sent: int = 0
    preferred_languages: dict[str, float] = Field(default_factory=dict)
    text_vs_voice_completion: dict[str, float] = Field(default_factory=dict)


class AiUsageBreakdown(_Out):
    text_cost_usd: float = 0.0
    vision_cost_usd: float = 0.0
    voice_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    remaining_budget_usd: float | None = None
    budget_ceiling_usd: float | None = None


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
    vision_analytics: VisionAnalytics = Field(default_factory=VisionAnalytics)
    emergency_alerts_today: int = 0
    emergency_avg_response_time: str | None = None
    active_critical_emergencies: int = 0
    voice_analytics: VoiceAnalytics = Field(default_factory=VoiceAnalytics)
    ai_usage: AiUsageBreakdown = Field(default_factory=AiUsageBreakdown)


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
    electrical_images: int = 0
    machine_images: int = 0
    chemical_images: int = 0
    other_images: int = 0


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
    input_method: str | None = None


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


class AuditVisionSuggestion(_Out):
    category: str | None = None
    confidence: float | None = None
    observations: list[str] = Field(default_factory=list)
    model_used: str | None = None
    timestamp: str | None = None
    final_decision: str | None = None
    override: bool = False
    override_reason: str | None = None
    changed_by: str | None = None
    suggestion_only: bool = True


class AuditVoiceReport(_Out):
    input_method: str = "Voice"
    audio_language: str | None = None
    transcription: str | None = None
    ai_cost: str | None = None
    human_override: str = "No"
    duration_seconds: float | None = None
    confidence_label: str | None = None
    audio_format: str | None = None
    voice_reply_sent: bool | None = None
    voice_language: str | None = None
    voice_model: str | None = None
    voice_cost_usd: float | None = None
    full_accessibility_loop: bool | None = None


class AuditEmergencyBypass(_Out):
    detected: bool = False
    reason: str | None = None
    trigger_keyword: str | None = None
    ai_triage: str | None = None
    response_time: str | None = None
    later_enrichment: str | None = None
    detection_time: str | None = None
    bypass_used: bool = False
    normal_ai_delayed: bool = False


class EmergencyActiveCard(_Out):
    incident_id: str
    location: str | None = None
    time: str | None = None
    response: str = "Team Notified"
    lifecycle: str | None = None
    channel: str | None = None
    trigger: str | None = None


class EmergencyTimelineEvent(_Out):
    time: str | None = None
    event: str


class EmergencyHistoryRow(_Out):
    incident_id: str
    trigger: str | None = None
    channel: str | None = None
    detection_time: str | None = None
    response_time: str | None = None
    resolution: str | None = None


class EmergencyMetrics(_Out):
    emergency_alerts_today: int = 0
    average_response_time: str | None = None
    active_critical_incidents: int = 0


class EmergencyCommandCenter(_Out):
    metrics: EmergencyMetrics = Field(default_factory=EmergencyMetrics)
    active: list[EmergencyActiveCard] = Field(default_factory=list)
    timeline: list[EmergencyTimelineEvent] = Field(default_factory=list)
    history: list[EmergencyHistoryRow] = Field(default_factory=list)


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
    vision_suggestion: AuditVisionSuggestion | None = None
    emergency_bypass: AuditEmergencyBypass | None = None
    voice_report: AuditVoiceReport | None = None
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


class HandoverMention(_Out):
    handover_id: str
    shift_label: str | None = None
    generated_at: datetime | str | None = None
    critical_open_count: int = 0


class HandoverGenerateIn(_Out):
    shift_label: str = "Evening Shift"


class HandoverRecord(_Out):
    handover_id: str
    shift_label: str | None = None
    summary_text: str | None = None
    open_incident_count: int = 0
    critical_open_count: int = 0
    generated_at: datetime | str | None = None
    generated_by: str | None = None
    new_incidents: int = 0
    human_review_required: int = 0
    awaiting_verification_overdue: int = 0
    top_risks: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    explainability: dict[str, Any] = Field(default_factory=dict)
    slack_posted: bool = False
    structured: dict[str, Any] = Field(default_factory=dict)
    incident_ids: list[str] = Field(default_factory=list)
    acknowledged: dict[str, Any] | None = None


class HandoverGenerateOut(_Out):
    success: bool = True
    handover: HandoverRecord


class HandoverHistoryOut(_Out):
    items: list[HandoverRecord] = Field(default_factory=list)
    total: int = 0


class HandoverAnalyticsOut(_Out):
    total_handovers: int = 0
    average_open_incidents: float = 0.0
    average_critical_alerts: float = 0.0
    most_common_shift_risks: list[dict[str, Any]] = Field(default_factory=list)
    compare: dict[str, Any] = Field(default_factory=dict)
    items: list[HandoverRecord] = Field(default_factory=list)


IncidentDetail.model_rebuild()
