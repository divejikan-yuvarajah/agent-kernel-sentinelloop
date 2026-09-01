import type {
  AnalyticsSummary,
  GuardrailComplianceExport,
  GuardrailConfigView,
  GuardrailDebugEvent,
  GuardrailStatus,
  IncidentSummary,
  RecurringHazard,
  ReviewQueueItem,
  RouterStatus,
  PredictionsResponse,
} from "@ds/types";

import type { AuditExport, EmergencyCommandCenter, IncidentDetail, IncidentListResponse } from "./client";
import {
  activity,
  categoryShare,
  duplicateGroup,
  evidenceRecords,
  incidents,
  kpis,
  monthlyTrend,
  notifications,
  organization,
  riskCounts,
  type DemoIncident,
} from "../data/demoData";
import { visionAnalysis } from "../data/demoImages";

const DEMO_NOW = Date.parse("2026-08-31T14:55:00+00:00");

function wait<T>(value: T, ms = 70): Promise<T> {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve(value), ms);
  });
}

function elapsedFrom(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "14m";
  const mins = Math.max(0, Math.round((DEMO_NOW - then) / 60000));
  if (mins < 60) return `${mins}m`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

function clockFrom(iso: string, addMinutes: number): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "10:01";
  date.setMinutes(date.getMinutes() + addMinutes);
  return date.toISOString().slice(11, 16);
}

function haystack(row: DemoIncident): string {
  return [
    row.incident_id,
    row.title,
    row.category,
    row.location,
    row.equipment,
    row.assigned_officer,
    row.assigned_team,
    row.reporter_name,
    row.original_text,
    row.translated_text,
    row.input_channel,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function loopStageFor(status: string): string {
  const key = status.toUpperCase().replace(/ /g, "_");
  if (key === "REPORTED" || key === "NEW") return "report";
  if (key === "ASSESSING" || key === "VALIDATING") return "understand";
  if (key === "OPEN" || key === "ASSESSED") return "assess";
  if (key === "ASSIGNED" || key === "ACCEPTED") return "alert";
  if (key === "IN_PROGRESS") return "act";
  if (key === "AWAITING_VERIFICATION") return "verify";
  if (key === "RESOLVED" || key === "CLOSED") return "learn";
  return "assess";
}

function toSummary(row: DemoIncident): IncidentSummary {
  return {
    incident_id: row.incident_id,
    title: row.title,
    category: row.category,
    location: row.location,
    status: row.status,
    risk_level: row.risk_level,
    risk_score: row.risk_score,
    created_at: row.created_at,
    updated_at: row.created_at,
    elapsed_time: elapsedFrom(row.created_at),
    assigned_officer: row.assigned_officer || null,
    assigned_team: row.assigned_team || null,
    reporter_name: row.reporter_name === "anonymous" ? "Anonymous" : row.reporter_name,
    duplicate_count: row.duplicate_count,
    loop_stage: row.loop_stage || loopStageFor(row.status),
    source: row.qr ? "QR_TAGGED" : row.input_channel || "telegram",
    location_verified: row.qr,
    qr_equipment: row.equipment,
    safety_status: row.risk_level === "CRITICAL" || row.risk_level === "HIGH" ? "Human Review Required" : "Validated",
    is_anonymous: row.reporter_name === "anonymous",
    input_channel: row.input_channel || (row.reporter_id.startsWith("telegram:") ? "telegram" : "telegram"),
    language: row.language,
    message_type: row.message_type || "text",
  };
}

function findIncident(id: string): DemoIncident | undefined {
  const wanted = decodeURIComponent(id);
  return incidents.find((row) => row.incident_id === wanted);
}

export function fetchIncidents(params: Record<string, string | number | undefined> = {}): Promise<IncidentListResponse> {
  const risk = String(params.risk_level || "").toUpperCase();
  const stage = String(params.stage || "").toLowerCase();
  const limit = Number(params.limit) || 50;
  const offset = Number(params.offset) || 0;
  const search = String(params.search || params.q || "")
    .trim()
    .toLowerCase();
  let items = [...incidents]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .filter((row) => (search ? haystack(row).includes(search) : true))
    .map(toSummary);
  if (risk && risk !== "ALL") {
    items = items.filter((row) => (row.risk_level || "").toUpperCase() === risk);
  }
  const channel = String(params.source_channel || params.channel || "").toLowerCase();
  if (channel && channel !== "all") {
    items = items.filter((row) => {
      const source = (row.source || "").toLowerCase();
      const input = (row.input_channel || "").toLowerCase();
      if (channel === "qr") return source === "qr_tagged" || input === "qr";
      return input === channel;
    });
  }
  const language = String(params.language || "").toLowerCase();
  if (language && language !== "all") {
    items = items.filter((row) => (row.language || "").toLowerCase().startsWith(language.slice(0, 2)) || (row.language || "").toLowerCase() === language);
  }
  const messageType = String(params.message_type || "").toLowerCase();
  if (messageType && messageType !== "all") {
    items = items.filter((row) => (row.message_type || "text").toLowerCase() === messageType);
  }
  if (stage) {
    items = items.filter((row) => row.loop_stage === stage);
  }
  const page = items.slice(offset, offset + limit);
  return wait({
    items: page,
    total: items.length,
    limit,
    offset,
    sort_by: String(params.sort_by || "newest"),
    sort_order: "desc",
  });
}

export function fetchIncident(id: string): Promise<IncidentDetail> {
  const row = findIncident(id);
  if (!row) {
    return Promise.reject(new Error("incident not found"));
  }
  const related = incidents.filter(
    (item) => item.incident_id !== row.incident_id && item.category === row.category && item.location === row.location,
  );
  const ev = evidenceRecords.filter((item) => item.incident_id === row.incident_id);
  const voiceEvents =
    row.message_type === "voice"
      ? [
          { timestamp: clockFrom(row.created_at, 0), title: "Voice message received", detail: row.input_channel || "voice", actor: "worker" },
          {
            timestamp: clockFrom(row.created_at, 1),
            title: "Audio transcribed",
            detail: row.translated_text,
            actor: "voice_tools",
          },
          {
            timestamp: clockFrom(row.created_at, 1),
            title: "Language detected",
            detail: row.language,
            actor: "voice_tools",
          },
          { timestamp: clockFrom(row.created_at, 2), title: "Incident created", detail: row.incident_id, actor: "incident_agent" },
        ]
      : [];
  const timeline = row.emergency
    ? [
        { timestamp: "10:32:01", title: "Emergency keyword detected", detail: row.emergency_trigger || "🔥", actor: "emergency_bypass" },
        { timestamp: "10:32:02", title: "Critical incident created", detail: row.incident_id, actor: "repository" },
        { timestamp: "10:32:03", title: "Slack alert sent", detail: "Emergency Response Channel", actor: "slack" },
        { timestamp: "10:32:04", title: "Worker notified", detail: "Fixed safety reply", actor: "telegram" },
        { timestamp: "10:34:20", title: "AI enrichment completed", detail: row.category, actor: "intake_agent" },
      ]
    : [
        { timestamp: clockFrom(row.created_at, 0), title: "Worker uploaded image", detail: row.input_channel || "image", actor: "worker" },
    { timestamp: clockFrom(row.created_at, 1), title: "Vision AI analyzed image", detail: "role_vision", actor: "incident_agent" },
    {
      timestamp: clockFrom(row.created_at, 1),
      title: `Suggested ${visionAnalysis(row.incident_id, row.category).hazard} hazard`,
      detail: `Confidence ${visionAnalysis(row.incident_id, row.category).confidence}%`,
      actor: "role_vision",
    },
    {
      timestamp: clockFrom(row.created_at, 1),
      title: `Language detected: ${row.language}`,
      detail: row.translated_text,
      actor: "intake_agent",
    },
    { timestamp: clockFrom(row.created_at, 1), title: "Hazard classified", detail: row.category, actor: "intake_agent" },
    { timestamp: clockFrom(row.created_at, 2), title: "Incident confirmed", detail: row.category, actor: "incident_agent" },
    {
      timestamp: clockFrom(row.created_at, 2),
      title: "Duplicate check completed",
      detail: `${row.duplicate_count} report(s)`,
      actor: "duplicate_tools",
    },
    { timestamp: clockFrom(row.created_at, 2), title: "Risk calculated", detail: row.risk_explanation, actor: "risk_agent" },
    { timestamp: clockFrom(row.created_at, 3), title: "Guidance sent", detail: row.guidance, actor: "guidance_agent" },
    {
      timestamp: clockFrom(row.created_at, 4),
      title: "Slack notification created",
      detail: row.assigned_team,
      actor: "coordination_agent",
    },
  ];
  if (voiceEvents.length) {
    timeline.unshift(...voiceEvents);
  }
  const detail: IncidentDetail = {
    incident_id: row.incident_id,
    title: row.title,
    description: row.translated_text,
    category: row.category,
    location: row.location,
    reporter: {
      reporter_id: row.reporter_name === "anonymous" ? "anonymous" : row.reporter_id,
      source_channel: row.input_channel || (row.reporter_id.startsWith("telegram:") ? "telegram" : "telegram"),
      language: row.language,
    },
    created_at: row.created_at,
    updated_at: row.created_at,
    status: row.status,
    elapsed_time: elapsedFrom(row.created_at),
    assigned_officer: row.assigned_officer || null,
    loop_stage: row.loop_stage,
    risk: {
      risk_level: row.risk_level,
      risk_score: row.risk_score,
      ai_confidence: 0.946,
      risk_explanation: row.risk_explanation,
      detected_hazards: [row.category, row.equipment || row.location, `${row.people_exposed} people exposed`].filter(Boolean),
      reasoning_summary: row.risk_explanation,
    },
    evidence: ev.map((item) => ({
      evidence_id: item.id,
      kind: item.kind,
      label: item.label,
      source: item.source,
      stage: item.stage,
      uploaded_at: item.date,
      has_image: item.kind === "image",
      storage_available: true,
      uploaded_by: "uploaded_by" in item ? String(item.uploaded_by || "") : undefined,
      content_kind: item.kind,
    })),
    timeline,
    duplicates: {
      duplicate_count: row.duplicate_count,
      linked_incidents: related.slice(0, 3).map((item) => ({
        incident_id: item.incident_id,
        title: item.title,
        status: item.status,
        similarity_score: 0.86,
      })),
      duplicate_similarity_score: row.duplicate_count > 1 ? 0.86 : null,
    },
    source: row.qr ? "QR_TAGGED" : row.input_channel || (row.reporter_id.startsWith("telegram:") ? "telegram" : "telegram"),
    location_verified: row.qr,
    qr_equipment: row.equipment,
    location_confidence: row.qr ? 1 : null,
    is_anonymous: row.reporter_name === "anonymous",
    input_channel: row.input_channel || (row.reporter_id.startsWith("telegram:") ? "telegram" : "telegram"),
    voice_report:
      row.message_type === "voice" || row.incident_id === "INC-2026-00422"
        ? {
            duration_seconds: row.voice_duration_seconds ?? 18,
            language: row.language === "Sinhala" ? "si" : row.language === "Tamil" ? "ta" : "en",
            language_name: row.language,
            transcript: row.translated_text,
            audio_format: "ogg",
            input_method: "voice",
            audio_used: true,
            transcription_cost: 0.001,
            transcription_confidence: 0.92,
            confidence_label: "High confidence 92%",
            processing_status: "Completed",
            playback_url: null,
            uploaded_by: "Worker",
            source: row.input_channel === "telegram" ? "Telegram" : "Telegram",
          }
        : null,
    input_method: row.message_type === "voice" ? "voice" : row.input_channel === "manual" ? "dashboard" : "text",
    created_by: row.input_channel === "manual" ? row.reporter_name : null,
    pipeline_stages: [
      { name: "Translation", completed: true },
      { name: "Hazard Extraction", completed: true },
      { name: "Risk Calculation", completed: true, detail: row.risk_level },
      { name: "Guidance Selection", completed: true },
      { name: "Team Assignment", completed: Boolean(row.assigned_team) },
    ],
    safety_status:
      row.guidance_status === "blocked"
        ? "Guardrail Blocked"
        : row.risk_level === "CRITICAL" || row.risk_level === "HIGH"
          ? "Human Review Required"
          : "Validated",
    safety: {
      incident_id: row.incident_id,
      safety_status: row.guidance_status === "blocked" ? "Guardrail Blocked" : "Validated",
      risk_level: row.risk_level,
      human_review: row.risk_level === "CRITICAL" || row.risk_level === "HIGH" ? "Required" : "Not required",
      guidance: row.guidance,
      closure: row.status === "CLOSED" ? "Closed by authorized officer" : "Blocked until officer approval",
      auto_close_disabled: row.risk_level === "CRITICAL" || row.risk_level === "HIGH",
      guidance_verification: {
        knowledge_base_file: row.knowledge_base,
        supported_lines: "1 matched line",
        hallucination_check: row.guidance_status === "blocked" ? "Blocked" : "Passed",
        generated_guidance: row.guidance,
      },
      timeline: [
        { timestamp: row.created_at, title: "Input validated", detail: "Length and attachments within policy" },
        {
          timestamp: row.created_at,
          title: row.guidance_status === "blocked" ? "Guidance blocked" : "Guidance approved",
          detail: row.knowledge_base,
        },
      ],
      assigned_reviewer: row.assigned_officer || organization.operator.name,
    },
    original_text: row.original_text,
    translated_text: row.translated_text,
    language: row.language,
    equipment: row.equipment,
    people_exposed: row.people_exposed,
    hazard_active: row.active,
    injury: row.injury,
    assigned_team: row.assigned_team,
    severity: row.severity,
    likelihood: row.likelihood,
    vision: {
      hazard_category: visionAnalysis(row.incident_id, row.category).hazard,
      confidence: visionAnalysis(row.incident_id, row.category).confidence / 100,
      observations: visionAnalysis(row.incident_id, row.category).objects,
      model_used: "qwen/qwen-vl-free",
      timestamp: row.created_at,
      suggestion_only: true,
      final_category: row.category,
      vision_override: false,
      override_reason: null,
      changed_by: null,
      confidence_band:
        visionAnalysis(row.incident_id, row.category).confidence >= 90
          ? "high"
          : visionAnalysis(row.incident_id, row.category).confidence >= 60
            ? "medium"
            : "low",
    },
    included_in_handovers:
      row.incident_id === "INC-2026-00421"
        ? [{ handover_id: "ho-evening", shift_label: "Evening Shift", generated_at: "2026-09-01T22:01:00+00:00", critical_open_count: 1 }]
        : row.incident_id === "INC-2026-00420"
          ? [{ handover_id: "ho-morning", shift_label: "Morning Shift", generated_at: "2026-09-01T14:01:00+00:00", critical_open_count: 2 }]
          : [],
  };
  return wait(detail);
}

export function fetchAnalyticsSummary(): Promise<AnalyticsSummary> {
  const loop = [
    { stage: "report", label: "Report", count: 2, percentage: 8.3 },
    { stage: "understand", label: "Understand", count: 1, percentage: 4.2 },
    { stage: "assess", label: "Assess", count: 2, percentage: 8.3 },
    { stage: "alert", label: "Alert", count: 8, percentage: 33.3 },
    { stage: "act", label: "Act", count: 5, percentage: 20.8 },
    { stage: "verify", label: "Verify", count: 2, percentage: 8.3 },
    { stage: "learn", label: "Learn", count: 4, percentage: 16.7 },
  ];
  return wait({
    total_incidents: kpis.totalIncidents,
    open_incidents: kpis.openIncidents,
    critical_incidents: kpis.criticalIncidents,
    resolved_today: kpis.resolvedThisMonth,
    avg_response_time: kpis.averageResponseTime,
    incidents_last_24_hours: 11,
    incidents_last_7_days: 28,
    incidents_by_risk_level: {
      LOW: riskCounts.LOW,
      MEDIUM: riskCounts.MEDIUM,
      HIGH: riskCounts.HIGH,
      CRITICAL: riskCounts.CRITICAL,
    },
    incidents_by_category: {
      electrical: 86,
      machine: 49,
      chemical: 37,
      "fire/smoke": 25,
      "slip/trip": 30,
      "missing PPE": 20,
    },
    average_resolution_time: kpis.averageResolution,
    fastest_response_time: kpis.averageDetection,
    slowest_response_time: "38 minutes",
    loop_stages: loop,
    recent_activity: activity.map((item) => ({
      timestamp: item.timestamp,
      kind: item.kind,
      summary: item.summary,
      incident_id: item.incident_id,
    })),
    qr_tagged_incidents: incidents.filter((row) => row.qr).length,
    top_qr_locations: [
      { location: "CNC Area", equipment: "CNC-04", count: 4, risk_score: 25, insight: "Recurring electrical reports" },
      { location: "Welding Section", equipment: "Welder-07", count: 2, risk_score: 20, insight: null },
    ],
    most_repeated_hazards: [
      {
        label: "electrical · CNC Area",
        location: "CNC Area",
        count: 3,
        insight: "This equipment has recurring reports. Consider inspection.",
      },
    ],
    repeated_hazard_locations: [{ label: "CNC Area", location: "CNC Area", count: 3, insight: null }],
    duplicate_detection_stats: { groups_checked: 41, duplicates_merged: 12, escalations: 3 },
    reports_by_channel: [
      { channel: "telegram", count: 136, percentage: 55 },
      { channel: "manual", count: 74, percentage: 30 },
      { channel: "qr", count: 37, percentage: 15 },
    ],
    telegram_message_types: { Text: 60, Image: 25, Voice: 15 },
    telegram_languages: { Sinhala: 45, Tamil: 35, English: 20 },
    monthly_trend: monthlyTrend,
    category_share: categoryShare,
    resolved_this_month: kpis.resolvedThisMonth,
    ai_detection_accuracy: kpis.aiDetectionAccuracy,
    worker_languages: kpis.languages,
    anonymous_reports: kpis.anonymousReports,
    average_detection: kpis.averageDetection,
    average_assignment: kpis.averageAssignment,
    emergency_alerts_today: 12,
    emergency_avg_response_time: "1.8 seconds",
    active_critical_emergencies: 4,
    voice_analytics: {
      reports_today: 42,
      average_transcription_seconds: 2.1,
      most_used_language: "Sinhala",
      languages: { Sinhala: 60, Tamil: 25, English: 15 },
      incident_sources: { Text: 55, Voice: 30, Image: 15 },
      completion_rate_voice: 92,
      completion_rate_text: 81,
    },
    ai_usage: {
      text_cost_usd: 2.4,
      vision_cost_usd: 0.8,
      voice_cost_usd: 0.35,
      total_cost_usd: 3.55,
      remaining_budget_usd: 6.45,
      budget_ceiling_usd: 10,
    },
    vision_analytics: {
      images_analyzed: 142,
      high_confidence_detections: 87,
      human_overrides: 12,
      average_confidence: 0.84,
      confidence_distribution: { high: 70, medium: 25, low: 5 },
      hazard_detection_by_image: [
        { label: "Electrical", percent: 45, count: 64 },
        { label: "Chemical", percent: 20, count: 28 },
        { label: "Machine", percent: 15, count: 21 },
        { label: "Slip", percent: 10, count: 14 },
        { label: "Other", percent: 10, count: 15 },
      ],
      model_usage: { free_percent: 90, paid_percent: 10, average_cost_usd: 0.002 },
      location_heatmap: [
        {
          location: "CNC Area",
          risk: "HIGH",
          electrical_images: 12,
          machine_images: 7,
          chemical_images: 0,
          other_images: 1,
          total_images: 20,
        },
      ],
    },
  });
}

export function fetchRecurring(): Promise<{ items: RecurringHazard[] }> {
  return wait({
    items: [
      {
        category: duplicateGroup.category,
        location: duplicateGroup.location,
        count: duplicateGroup.reports,
        period: duplicateGroup.period,
        severity: "CRITICAL",
        recommendation: "Requires preventive action",
        recurrence_percentage: 12.5,
        trend_direction: "up",
        first_seen: "2026-01-12T08:00:00+00:00",
        last_seen: "2026-02-02T09:00:00+00:00",
      },
      {
        category: "chemical",
        location: "Chemical Storage Room",
        count: 3,
        period: "30 days",
        severity: "HIGH",
        recommendation: "Requires preventive action",
        recurrence_percentage: 8.1,
        trend_direction: "stable",
        first_seen: "2026-08-01T08:00:00+00:00",
        last_seen: "2026-08-29T09:48:00+00:00",
      },
    ],
  });
}

export function fetchPredictions(): Promise<PredictionsResponse> {
  const lastUpdated = new Date(Date.now() - 4 * 60 * 1000).toISOString();
  return wait({
    generated_at: lastUpdated,
    last_updated: lastUpdated,
    prediction_count: 3,
    weekly_counts: [2, 3, 5, 7],
    analytics: {
      predicted_risk_zones: 3,
      resolved_future_risks: 1,
      inspections_triggered: 2,
      prevented_recurrences: 1,
    },
    heatmap: [
      { location: "Electrical Room", risk: "CRITICAL", marker: "🔴", active: 4, predicted: true },
      { location: "CNC Area", risk: "HIGH", marker: "🟠", active: 3, predicted: true, electrical_images: 12, machine_images: 7 },
      { location: "Loading Bay", risk: "MEDIUM", marker: "🟡", active: 2, predicted: true },
      { location: "Office Area", risk: "LOW", marker: "🟢", active: 1, predicted: false },
    ],
    predictions: [
      {
        location: "CNC Area",
        category: "electrical",
        reason: "4 related incidents detected",
        recommendation: "Inspect electrical panel before next shift.",
        trend: "increasing",
        incident_count: 4,
        frequency_score: 0.38,
        risk_level: "High",
        reason_factors: [
          "4 incidents detected",
          "same location",
          "increasing frequency",
          "recent active report",
        ],
        weekly_counts: [1, 1, 1, 1],
        generated_by: "prevention_agent",
        confidence: 0.91,
        prediction_id: "cnc-area__electrical",
        location_hotspot: true,
        days_since_last: 0,
        span_days: 21,
        timeline: [
          { date: "2026-08-10", label: "Incident reported" },
          { date: "2026-08-18", label: "Duplicate detected" },
          { date: "2026-08-30", label: "Pattern identified" },
          { date: "2026-08-31", label: "Inspection recommended" },
        ],
      },
      {
        location: "Chemical Storage Room",
        category: "chemical",
        reason: "3 chemical leak reports detected",
        recommendation: "Schedule a supervisor review of chemical storage before the next shift.",
        trend: "increasing",
        incident_count: 3,
        frequency_score: 0.31,
        risk_level: "High",
        reason_factors: ["3 reports in 25 days", "same location", "high frequency"],
        weekly_counts: [0, 1, 1, 1],
        generated_by: "prevention_agent",
        confidence: 0.88,
        prediction_id: "chemical-storage-room__chemical",
        location_hotspot: false,
        days_since_last: 1,
        span_days: 25,
        timeline: [
          { date: "2026-08-06", label: "Incident reported" },
          { date: "2026-08-29", label: "Pattern identified" },
          { date: "2026-08-31", label: "Inspection recommended" },
        ],
      },
      {
        location: "Loading Bay",
        category: "slip/trip",
        reason: "2 related incidents detected",
        recommendation: "Inspect walkways and spill controls at Loading Bay before the next shift.",
        trend: "stable",
        incident_count: 2,
        frequency_score: 0.22,
        risk_level: "Medium",
        reason_factors: ["2 reports in 16 days", "same location", "stable reporting interval"],
        weekly_counts: [0, 1, 0, 1],
        generated_by: "prevention_agent",
        confidence: 0.7,
        prediction_id: "loading-bay__slip/trip",
        location_hotspot: false,
        days_since_last: 4,
        span_days: 16,
        timeline: [
          { date: "2026-08-15", label: "Incident reported" },
          { date: "2026-08-27", label: "Pattern identified" },
          { date: "2026-08-31", label: "Inspection recommended" },
        ],
      },
    ],
  });
}

export function requestInspection(_payload: {
  location: string;
  category?: string | null;
  reason?: string | null;
  recommendation?: string | null;
}) {
  return wait({ posted: true, message_type: "inspection_request", coordination_error: null });
}

export function fetchRouterStatus(): Promise<RouterStatus> {
  return wait({
    budget: { budget_limit: 3, spent: 1.12, remaining: 1.88, usage_percentage: 37.3 },
    recent_calls: [
      {
        timestamp: "2026-08-31T13:13:00+00:00",
        model: "mistralai/mistral-nemo",
        model_role: "role_reasoning",
        agent_role: "risk_agent",
        tier: "SMART MODEL",
        latency_s: 1.8,
        token_usage: { prompt_tokens: 420, completion_tokens: 110, total_tokens: 530 },
        cost_usd: 0.012,
      },
    ],
    request_count: 186,
    paid_call_count: 22,
    ledger_available: true,
  });
}

export function fetchAiUsage() {
  return wait({
    text_cost_usd: 2.4,
    vision_cost_usd: 0.8,
    voice_cost_usd: 0.35,
    total_cost_usd: 3.55,
    remaining_budget_usd: 6.45,
    budget_ceiling_usd: 10,
  });
}

export function fetchAuditExport(id: string): Promise<AuditExport> {
  const row = findIncident(id);
  if (!row) return Promise.reject(new Error("incident not found"));
  return wait({
    incident_information: {
      incident_id: row.incident_id,
      title: row.title,
      category: row.category,
      location: row.location,
      equipment: row.equipment,
      created_at: row.created_at,
      current_status: row.status,
      current_risk_level: row.risk_level,
      duplicate_count: row.duplicate_count,
    },
    original_report: {
      source: row.qr ? "QR_TAGGED" : row.input_channel || "telegram",
      message: row.original_text,
      received_at: row.created_at,
      worker_identifier: row.reporter_name === "anonymous" ? "anonymous" : "worker",
      communication_channel: row.input_channel === "telegram" ? "Telegram" : "Telegram",
      input_method: row.message_type === "voice" ? "Voice" : "Text",
    },
    language_processing: {
      detected_language: row.language,
      language: row.language,
      original_text: row.original_text,
      translated_text: row.translated_text,
      translation_timestamp: row.created_at,
    },
    extracted_information: {
      fields: [
        { field: "hazard", value: row.category, confidence: 0.96 },
        { field: "location", value: row.location, confidence: 0.94 },
        { field: "equipment", value: row.equipment, confidence: 0.9 },
        { field: "people_exposed", value: String(row.people_exposed), confidence: 0.88 },
      ],
    },
    ai_decision: {
      severity: String(row.severity),
      likelihood: String(row.likelihood),
      confidence: 0.946,
      detected_risks: [row.category],
      reasoning_summary: row.risk_explanation,
      ai_recommendation: row.guidance,
      human_final_decision: row.assigned_officer ? "Officer assigned" : null,
      override_reason: null,
      explanation_label: "Deterministic risk matrix",
    },
    risk_analysis: {
      score: row.risk_score,
      base_risk_level: row.risk_level,
      final_risk_level: row.risk_level,
      calculation_factors: [`severity ${row.severity}`, `likelihood ${row.likelihood}`, `${row.people_exposed} exposed`],
      explanation: row.risk_explanation,
      rule_validation: "Passed",
    },
    guidance_history: [
      {
        guidance: row.guidance,
        language: row.language,
        timestamp: row.created_at,
        source: row.knowledge_base,
        section: row.knowledge_base,
        matched_text: row.guidance,
        line_reference: "1",
        rule_id: row.knowledge_base,
      },
    ],
    coordination_history: [
      { event: "Slack alert posted", channel: "#electrical-safety", time: row.created_at, detail: row.assigned_team },
    ],
    assignment_history: [
      { officer: row.assigned_officer, previous_officer: null, assigned_at: row.created_at, reason: "Team match" },
    ],
    incident_timeline: [
      { time: row.created_at, event: "Worker uploaded image", update_type: "evidence_added", message: row.translated_text, created_by: "worker" },
      { time: row.created_at, event: "Vision AI analyzed image", update_type: "vision_suggestion", message: "Suggestion only", created_by: "role_vision" },
      { time: row.created_at, event: "Incident confirmed", update_type: "intake_completed", message: row.category, created_by: "incident_agent" },
    ],
    vision_suggestion: {
      category: visionAnalysis(row.incident_id, row.category).hazard,
      confidence: visionAnalysis(row.incident_id, row.category).confidence / 100,
      observations: visionAnalysis(row.incident_id, row.category).objects,
      model_used: "qwen/qwen-vl-free",
      timestamp: row.created_at,
      final_decision: row.category,
      override: false,
      override_reason: null,
      changed_by: null,
      suggestion_only: true,
    },
    emergency_bypass: row.emergency
      ? {
          detected: true,
          reason: "Emergency keyword detected",
          trigger_keyword: row.emergency_trigger || "🔥",
          ai_triage: "Skipped initially",
          response_time: "1.4 seconds",
          later_enrichment: "Completed",
          detection_time: row.created_at,
          bypass_used: true,
          normal_ai_delayed: true,
        }
      : null,
    voice_report:
      row.message_type === "voice" || row.incident_id === "INC-2026-00422"
        ? {
            input_method: "Voice",
            audio_language: row.language,
            transcription: row.translated_text,
            ai_cost: "$0.001",
            human_override: "No",
            duration_seconds: row.voice_duration_seconds ?? 18,
            confidence_label: "High confidence 92%",
            audio_format: "ogg",
          }
        : null,
    resolution: {
      status: row.status,
      resolution_message: row.status === "CLOSED" ? "Worker confirmed the area is safe." : null,
      resolved_by: row.status === "CLOSED" ? row.assigned_officer : null,
      resolved_timestamp: row.status === "CLOSED" ? row.created_at : null,
      evidence: evidenceRecords.filter((item) => item.incident_id === row.incident_id).map((item) => item.label),
      verification_status: row.status === "AWAITING_VERIFICATION" ? "Pending" : row.status === "CLOSED" ? "Worker confirmed" : null,
      human_verification: row.status === "CLOSED" ? "Officer confirmed resolution." : null,
    },
    audit_metadata: {
      export_timestamp: "2026-08-31T13:30:00+00:00",
      system_version: "sentinelloop-demo",
      audit_export_version: "1.0",
      models_used: ["mistralai/mistral-nemo"],
      ai_calls: 4,
      estimated_cost: "0.04",
      total_processing_time: "12s",
      audit_hash: "demo-audit-horizon",
      compliance: ["guidance grounded", "human review for critical"],
    },
  });
}

export function fetchGuardrailStatus(): Promise<GuardrailStatus> {
  return wait({
    cards: [
      { name: "Input Validation", active: true, spec_rule: "Length, attachments, injection" },
      { name: "Guidance Grounding", active: true, spec_rule: "Knowledge-base only" },
      { name: "Human Review Protection", active: true, spec_rule: "Human intervention for Critical incidents" },
      { name: "Privacy Redaction", active: true, spec_rule: "Anonymous analytics" },
    ],
    metrics: { total_validations: 186, passed: 179, blocked: 5, warnings: 2 },
    violations: { guidance_hallucinations: 5, privacy_attempts: 2, blocked_closures: 3, budget_blocks: 0 },
    charts: {
      guidance_validation_success_rate: 96.2,
      incidents_requiring_human_review: 6,
      blocked_ai_outputs: 5,
      anonymous_reports_percentage: 25.5,
      average_ai_cost_per_incident: 0.04,
    },
    budget_ceiling_usd: 3,
    budget_spent_usd: 1.12,
  });
}

export function fetchReviewQueue(): Promise<{ items: ReviewQueueItem[]; total: number }> {
  const items = incidents
    .filter((row) => (row.risk_level === "CRITICAL" || row.risk_level === "HIGH") && row.status !== "CLOSED")
    .slice(0, 6)
    .map((row) => ({
      incident_id: row.incident_id,
      risk_level: row.risk_level,
      reason: "Human approval required according to SPEC.md",
      assigned_reviewer: row.assigned_officer || "Kasun Perera",
      waiting_time: "12m",
      status: row.status,
      actions: ["Approve Closure", "Reject", "Request More Info"],
      actions_enabled: false,
      action_hint: "Closure is performed with the Slack Closed button. This dashboard is read-only.",
    }));
  return wait({ items, total: items.length });
}

export function fetchGuardrailDebug(): Promise<GuardrailDebugEvent[]> {
  return wait([
    {
      timestamp: "2026-08-31T13:16:20+00:00",
      guardrail: "guidance_grounding",
      event: "blocked",
      input_summary: "Turn off the electrical supply yourself.",
      validation_result: "blocked",
      agent_output: "Invented instruction",
      rule_violated: "Must match knowledge base",
      decision: "Released knowledge-base fallback",
      incident_id: "INC-2026-00415",
      violations: ["ungrounded_instruction"],
    },
    {
      timestamp: "2026-08-31T13:13:40+00:00",
      guardrail: "guidance_grounding",
      event: "approved",
      input_summary: "Keep away from exposed wires, sparks, smoke, or damaged electrical equipment.",
      validation_result: "passed",
      agent_output: "Grounded line from electrical_safety.md",
      rule_violated: null,
      decision: "Released to worker",
      incident_id: "INC-2026-00421",
      violations: [],
    },
  ]);
}

export function fetchGuardrailConfig(): Promise<GuardrailConfigView> {
  return wait({
    ai_budget_ceiling: "3",
    guidance_validation_strictness: "strict",
    anonymous_data_policy: "redact identifiers",
    closure_rules: "High/Critical require officer Slack Closed",
    max_text_length: 4000,
    max_attachment_bytes: 8_000_000,
    writable: false,
  });
}

export function fetchComplianceExport(): Promise<GuardrailComplianceExport> {
  return wait({
    generated_at: "2026-08-31T13:30:00+00:00",
    validation_history: [{ incident: "INC-2026-00421", result: "approved" }],
    violations: { guidance_hallucinations: 5, privacy_attempts: 2, blocked_closures: 3, budget_blocks: 0 },
    human_approvals: 14,
    incident_count: kpis.totalIncidents,
    ai_spend_usd: 1.12,
    budget_ceiling_usd: 3,
    audit_note: "AI does not control safety-critical outcomes without validation.",
  });
}

export function fetchEmergencies(): Promise<EmergencyCommandCenter> {
  const emergencyRows = incidents.filter((row) => row.emergency || row.category === "unspecified-emergency" || row.risk_level === "CRITICAL");
  const featured = incidents.find((row) => row.incident_id === "INC-00421") || emergencyRows[0];
  return wait({
    metrics: {
      emergency_alerts_today: 12,
      average_response_time: "1.8 seconds",
      active_critical_incidents: 4,
    },
    active: featured
      ? [
          {
            incident_id: featured.incident_id,
            location: featured.location,
            time: "10:32 AM",
            response: "Team Notified",
            lifecycle: "Critical Review",
            channel: featured.input_channel || "telegram",
            trigger: featured.emergency_trigger || "🔥",
          },
        ]
      : [],
    timeline: [
      { time: "10:32:01", event: "Emergency keyword detected" },
      { time: "10:32:02", event: "Critical incident created" },
      { time: "10:32:03", event: "Slack alert sent" },
      { time: "10:32:04", event: "Worker notified" },
      { time: "10:34:20", event: "AI enrichment completed" },
    ],
    history: emergencyRows.slice(0, 8).map((row) => ({
      incident_id: row.incident_id,
      trigger: row.emergency_trigger || (row.emergency ? "SOS" : "🔥"),
      channel: row.input_channel || "telegram",
      detection_time: row.created_at,
      response_time: "1.4 seconds",
      resolution: row.status === "CLOSED" || row.status === "RESOLVED" ? "Resolved" : "Critical Review",
    })),
  });
}

export function fetchTelegramHealth() {
  return wait({
    connected: true,
    polling_active: true,
    last_message_at: "2026-08-31T14:53:00+00:00",
    last_message: "2 minutes ago",
    errors: 0,
    messages_today: 18,
    active_sessions: 6,
    voice_reports: 3,
    image_reports: 5,
    emergency_reports: 1,
    text_reports: 10,
    message_types: { Text: 60, Image: 25, Voice: 15 },
    language_distribution: { Sinhala: 45, Tamil: 35, English: 20 },
  });
}

export function fetchSystemHealth() {
  const newest = incidents[0]?.created_at || null;
  return wait({
    telegram: "connected",
    slack: "connected",
    database: "connected",
    ai_services: "available",
    last_incident: newest,
    last_incident_label: newest ? "2 min ago" : "no incidents yet",
    demo_mode: true,
  });
}

export type ManualIncidentPayload = {
  description: string;
  category: string;
  location: string;
  equipment_involved?: string;
  people_exposed: number;
  is_active: boolean;
  injury_reported: boolean;
  photo_base64?: string;
  photo_filename?: string;
  photo_content_type?: string;
  reporter_name?: string;
  created_by?: string;
  simulate?: boolean;
  scenario?: string;
};

function nextDemoId() {
  return `INC-${String(430 + incidents.length).padStart(5, "0")}`;
}

function pushDemoIncident(row: DemoIncident) {
  incidents.unshift(row);
  activity.unshift({
    timestamp: new Date().toISOString(),
    kind: "New report",
    summary: `${row.risk_level} incident received · ${row.location}`,
    incident_id: row.incident_id,
  });
  notifications.unshift({
    id: `N-${row.incident_id}`,
    title: row.risk_level === "CRITICAL" ? "Emergency response required" : "New hazard logged",
    body: `${row.incident_id} · ${row.location}`,
    time: "just now",
    severity: row.risk_level === "CRITICAL" ? "CRITICAL" : row.risk_level === "HIGH" ? "HIGH" : "MEDIUM",
  });
}

export function createManualIncident(payload: ManualIncidentPayload) {
  if (!payload.description.trim()) return Promise.reject(new Error("Description is required before creating incident"));
  if (payload.description.trim().length < 10) {
    return Promise.reject(new Error("Description must be at least 10 characters"));
  }
  if (!payload.location.trim()) return Promise.reject(new Error("Location is required before creating incident"));
  if (!payload.category.trim()) return Promise.reject(new Error("Category is required before creating incident"));
  if (!Number.isFinite(payload.people_exposed)) return Promise.reject(new Error("People exposed must be a number"));
  const id = nextDemoId();
  const now = new Date().toISOString();
  const reporter = (payload.reporter_name || payload.created_by || "").trim();
  pushDemoIncident({
    incident_id: id,
    title: payload.description.slice(0, 72),
    category: payload.category,
    location: payload.location,
    status: "ASSIGNED",
    risk_level: payload.is_active ? "CRITICAL" : "HIGH",
    risk_score: payload.is_active ? 20 : 12,
    created_at: now,
    assigned_officer: "A. Perera",
    assigned_team: "Electrical Maintenance",
    reporter_id: reporter ? `dashboard:${reporter}` : "dashboard:anonymous",
    reporter_name: reporter || "Anonymous",
    language: "English",
    original_text: payload.description,
    translated_text: payload.description,
    equipment: payload.equipment_involved || null,
    people_exposed: payload.people_exposed,
    active: payload.is_active,
    injury: payload.injury_reported,
    duplicate_count: 0,
    qr: false,
    loop_stage: "alert",
    severity: 5,
    likelihood: 4,
    risk_explanation: "Deterministic risk matrix (severity × likelihood, with active-hazard policy).",
    guidance: "Move away from the hazard and notify a supervisor.",
    knowledge_base: "fire_safety.md",
    guidance_status: "approved",
    input_channel: "manual",
    message_type: "text",
  });
  return wait({
    incident_id: id,
    status: "Assigned",
    risk_level: payload.is_active ? "CRITICAL" : "HIGH",
    risk_score: payload.is_active ? 20 : 12,
    risk_explanation: "Deterministic risk matrix (severity × likelihood, with active-hazard policy).",
    guidance_text: "Move away from the hazard and notify a supervisor.",
    pipeline: ["intake_agent", "incident_agent", "risk_agent", "guidance_agent", "coordination_agent", "repository"],
    slack_alert_sent: true,
    input_channel: "manual",
    input_method: "dashboard",
    error: null,
  });
}

export function simulateEmergencyReport(scenario = "smoke") {
  const samples: Record<string, ManualIncidentPayload> = {
    electrical: {
      description: "Electrical panel sparking near the isolator. Three workers nearby.",
      category: "Electrical",
      location: "Electrical Room",
      people_exposed: 3,
      is_active: true,
      injury_reported: false,
    },
    chemical: {
      description: "Chemical smell and a small leak at the storage cabinet.",
      category: "Chemical",
      location: "Chemical Storage",
      people_exposed: 2,
      is_active: true,
      injury_reported: false,
    },
    machine: {
      description: "Guard missing on machine 4. Belt is still running.",
      category: "Machine",
      location: "CNC Area",
      people_exposed: 4,
      is_active: true,
      injury_reported: false,
    },
    smoke: {
      description: "There is smoke coming from machine 4. Three workers are nearby.",
      category: "Fire/Smoke",
      location: "Machine 4",
      people_exposed: 3,
      is_active: true,
      injury_reported: false,
    },
  };
  return createManualIncident(samples[scenario] || samples.smoke);
}

const DEMO_HANDOVERS: Array<{
  handover_id: string;
  shift_label: string;
  summary_text: string;
  open_incident_count: number;
  critical_open_count: number;
  generated_at: string;
  generated_by: string;
  new_incidents: number;
  human_review_required: number;
  awaiting_verification_overdue: number;
  top_risks: { location: string; category: string; risk: string; incident_id: string }[];
  timeline: { time: string; event: string }[];
  explainability: {
    open_incidents: number;
    critical_incidents: number;
    pending_reviews: number;
    overdue_verification: number;
    note: string;
  };
  slack_posted: boolean;
}> = [
  {
    handover_id: "ho-evening",
    shift_label: "Evening Shift",
    summary_text:
      "Evening Shift Safety Handover\n\n• 3 new incidents reported\n• 8 incidents remain open\n• 1 Critical electrical incident requires attention\n• 2 High/Critical incidents awaiting human review\n• 1 verification request overdue\n\nPriority:\nInspect CNC Area electrical issue before next shift.",
    open_incident_count: 8,
    critical_open_count: 1,
    generated_at: "2026-09-01T22:01:00+00:00",
    generated_by: "handover_agent",
    new_incidents: 3,
    human_review_required: 2,
    awaiting_verification_overdue: 1,
    top_risks: [
      { location: "CNC Area", category: "Electrical", risk: "Critical", incident_id: "INC-2026-00421" },
      { location: "Chemical Storage", category: "Chemical Leak", risk: "High", incident_id: "INC-2026-00420" },
    ],
    timeline: [
      { time: "22:00", event: "Previous shift ended" },
      { time: "22:01", event: "Incidents collected" },
      { time: "22:01", event: "AI summary generated" },
      { time: "22:02", event: "Slack posted" },
    ],
    explainability: {
      open_incidents: 8,
      critical_incidents: 1,
      pending_reviews: 2,
      overdue_verification: 1,
      note: "The model only rewrote structured counts. It did not add incidents or risks.",
    },
    slack_posted: true,
  },
  {
    handover_id: "ho-morning",
    shift_label: "Morning Shift",
    summary_text:
      "Morning Shift Safety Handover\n\n• 5 new incidents reported\n• 9 incidents remain open\n• 2 Critical incidents still open\n• 3 High/Critical incidents awaiting human review\n• 1 verification request overdue\n\nPriority:\nInspect Chemical Storage leak verification before next shift.",
    open_incident_count: 9,
    critical_open_count: 2,
    generated_at: "2026-09-01T14:01:00+00:00",
    generated_by: "handover_agent",
    new_incidents: 5,
    human_review_required: 3,
    awaiting_verification_overdue: 1,
    top_risks: [
      { location: "Chemical Storage", category: "Chemical Leak", risk: "Critical", incident_id: "INC-2026-00420" },
      { location: "Welding Section", category: "Fire", risk: "Critical", incident_id: "INC-2026-00419" },
    ],
    timeline: [
      { time: "14:00", event: "Previous shift ended" },
      { time: "14:01", event: "Incidents collected" },
      { time: "14:01", event: "AI summary generated" },
      { time: "14:02", event: "Slack posted" },
    ],
    explainability: {
      open_incidents: 9,
      critical_incidents: 2,
      pending_reviews: 3,
      overdue_verification: 1,
      note: "The model only rewrote structured counts. It did not add incidents or risks.",
    },
    slack_posted: true,
  },
];

export function fetchLatestHandover() {
  return wait(DEMO_HANDOVERS[0]);
}

export function fetchHandoverHistory() {
  return wait({ items: DEMO_HANDOVERS, total: DEMO_HANDOVERS.length });
}

export function fetchHandoverAnalytics() {
  return wait({
    total_handovers: DEMO_HANDOVERS.length,
    average_open_incidents: 8.5,
    average_critical_alerts: 1.5,
    most_common_shift_risks: [
      { label: "CNC Area / Electrical", count: 1 },
      { label: "Chemical Storage / Chemical Leak", count: 2 },
    ],
    compare: {
      morning: { shift: "Morning Shift", critical: 2, open: 9 },
      evening: { shift: "Evening Shift", critical: 1, open: 8 },
    },
  });
}

export function generateHandover(shift_label: string) {
  const template = DEMO_HANDOVERS.find((item) => item.shift_label === shift_label) || DEMO_HANDOVERS[0];
  const created = {
    ...template,
    handover_id: `ho-${Date.now()}`,
    shift_label,
    generated_at: new Date().toISOString(),
    generated_by: "dashboard_officer",
  };
  DEMO_HANDOVERS.unshift(created);
  return wait({ success: true, handover: created });
}

export function exportHandoverJson(handoverId: string) {
  const found = DEMO_HANDOVERS.find((item) => item.handover_id === handoverId) || DEMO_HANDOVERS[0];
  return wait(found);
}

export async function exportHandoverPdf(handoverId: string) {
  const found = DEMO_HANDOVERS.find((item) => item.handover_id === handoverId) || DEMO_HANDOVERS[0];
  const text = found.summary_text;
  return new Blob([text], { type: "application/pdf" });
}
