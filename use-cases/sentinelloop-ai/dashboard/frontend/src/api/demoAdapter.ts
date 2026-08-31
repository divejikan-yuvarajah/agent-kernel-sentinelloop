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
} from "@ds/types";

import type { AuditExport, IncidentDetail, IncidentListResponse } from "./client";
import {
  activity,
  categoryShare,
  duplicateGroup,
  evidenceRecords,
  incidents,
  kpis,
  monthlyTrend,
  organization,
  riskCounts,
  type DemoIncident,
} from "../data/demoData";

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
    source: row.qr ? "QR_TAGGED" : "whatsapp",
    location_verified: row.qr,
    qr_equipment: row.equipment,
    safety_status: row.risk_level === "CRITICAL" || row.risk_level === "HIGH" ? "Human Review Required" : "Validated",
    is_anonymous: row.reporter_name === "anonymous",
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
  const timeline = [
    { timestamp: clockFrom(row.created_at, 0), title: "Worker message received", detail: row.original_text, actor: "worker" },
    {
      timestamp: clockFrom(row.created_at, 1),
      title: `Language detected: ${row.language}`,
      detail: row.translated_text,
      actor: "intake_agent",
    },
    { timestamp: clockFrom(row.created_at, 1), title: "Hazard classified", detail: row.category, actor: "intake_agent" },
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
  const detail: IncidentDetail = {
    incident_id: row.incident_id,
    title: row.title,
    description: row.translated_text,
    category: row.category,
    location: row.location,
    reporter: {
      reporter_id: row.reporter_name === "anonymous" ? "anonymous" : row.reporter_id,
      source_channel: "whatsapp",
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
    source: row.qr ? "QR_TAGGED" : "whatsapp",
    location_verified: row.qr,
    qr_equipment: row.equipment,
    location_confidence: row.qr ? 1 : null,
    is_anonymous: row.reporter_name === "anonymous",
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
    monthly_trend: monthlyTrend,
    category_share: categoryShare,
    resolved_this_month: kpis.resolvedThisMonth,
    ai_detection_accuracy: kpis.aiDetectionAccuracy,
    worker_languages: kpis.languages,
    anonymous_reports: kpis.anonymousReports,
    average_detection: kpis.averageDetection,
    average_assignment: kpis.averageAssignment,
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
      source: row.qr ? "QR_TAGGED" : "whatsapp",
      message: row.original_text,
      received_at: row.created_at,
      worker_identifier: row.reporter_name === "anonymous" ? "anonymous" : "worker",
      communication_channel: "whatsapp",
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
      { time: row.created_at, event: "Report received", update_type: "incident_created", message: row.translated_text, created_by: "intake_agent" },
    ],
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
