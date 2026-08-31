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

import { isDemoMode } from "../demo/demoMode";
import * as demo from "./demoAdapter";

const API_BASE = "/api";

export type IncidentListResponse = {
  items: IncidentSummary[];
  total: number;
  limit: number;
  offset: number;
  sort_by: string;
  sort_order: string;
};

export type IncidentDetail = {
  incident_id: string;
  title: string | null;
  description: string | null;
  category: string | null;
  location: string | null;
  reporter: { reporter_id: string; source_channel: string | null; language: string | null };
  created_at: string | null;
  updated_at: string | null;
  status: string;
  elapsed_time: string | null;
  assigned_officer: string | null;
  loop_stage: string | null;
  risk: {
    risk_level: string | null;
    risk_score: number | null;
    ai_confidence: number | null;
    risk_explanation: string | null;
    detected_hazards: string[];
    reasoning_summary: string | null;
  };
  evidence: {
    evidence_id: string;
    kind: string | null;
    label: string | null;
    source: string | null;
    stage: string | null;
    uploaded_at: string | null;
    has_image: boolean;
    storage_available: boolean;
    uploaded_by?: string | null;
    content_kind?: string | null;
  }[];
  timeline: { timestamp: string | null; title: string; detail: string | null; actor: string | null }[];
  duplicates: {
    duplicate_count: number;
    linked_incidents: {
      incident_id: string;
      title: string | null;
      status: string | null;
      similarity_score: number | null;
    }[];
    duplicate_similarity_score: number | null;
  };
  source?: string | null;
  location_verified?: boolean;
  qr_equipment?: string | null;
  location_confidence?: number | null;
  is_anonymous?: boolean;
  safety_status?: string | null;
  safety?: {
    incident_id: string;
    safety_status: string;
    risk_level: string | null;
    human_review: string;
    guidance: string;
    closure: string;
    auto_close_disabled: boolean;
    guidance_verification: {
      knowledge_base_file: string | null;
      supported_lines: string | null;
      hallucination_check: string | null;
      generated_guidance?: string | null;
    };
    timeline: { timestamp: string | null; title: string; detail: string | null }[];
    assigned_reviewer: string | null;
  } | null;
  original_text?: string | null;
  translated_text?: string | null;
  language?: string | null;
  equipment?: string | null;
  people_exposed?: number | null;
  hazard_active?: boolean | null;
  injury?: boolean | null;
  assigned_team?: string | null;
  severity?: number | null;
  likelihood?: number | null;
  input_channel?: string | null;
  voice_report?: {
    duration_seconds?: number | null;
    language?: string | null;
    transcript?: string | null;
    audio_format?: string | null;
  } | null;
  vision?: {
    hazard_category: string | null;
    confidence: number | null;
    observations: string[];
    model_used: string | null;
    timestamp: string | null;
    suggestion_only: boolean;
    final_category: string | null;
    vision_override: boolean;
    override_reason: string | null;
    changed_by: string | null;
    confidence_band: string | null;
  } | null;
};

async function getJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`);
  } catch {
    throw new Error("Dashboard API is not running. Start it on port 8000, then reload.");
  }
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();
  const looksLikeHtml = contentType.includes("text/html") || text.trimStart().startsWith("<");
  if (looksLikeHtml) {
    throw new Error("Dashboard API is not reachable. Start the SentinelLoop API on port 8000, then reload.");
  }
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      throw new Error("Dashboard API returned an invalid response.");
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body && typeof (body as { detail?: unknown }).detail === "string"
        ? (body as { detail: string }).detail
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("Dashboard API is not running. Start it on port 8000, then reload.");
  }
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text) as unknown;
    } catch {
      throw new Error("Dashboard API returned an invalid response.");
    }
  }
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body && typeof (body as { detail?: unknown }).detail === "string"
        ? (body as { detail: string }).detail
        : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return body as T;
}

export function fetchIncidents(params: Record<string, string | number | undefined> = {}) {
  if (isDemoMode()) return demo.fetchIncidents(params);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    query.set(key, String(value));
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return getJson<IncidentListResponse>(`/incidents${suffix}`);
}

export function fetchIncident(id: string) {
  if (isDemoMode()) return demo.fetchIncident(id);
  return getJson<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`);
}

export function fetchAnalyticsSummary() {
  if (isDemoMode()) return demo.fetchAnalyticsSummary();
  return getJson<AnalyticsSummary>("/analytics/summary");
}

export function fetchRecurring() {
  if (isDemoMode()) return demo.fetchRecurring();
  return getJson<{ items: RecurringHazard[] }>("/analytics/recurring");
}

export function fetchPredictions() {
  if (isDemoMode()) return demo.fetchPredictions();
  return getJson<PredictionsResponse>("/analytics/predictions");
}

export function requestInspection(payload: {
  location: string;
  category?: string | null;
  reason?: string | null;
  recommendation?: string | null;
}) {
  if (isDemoMode()) return demo.requestInspection(payload);
  return postJson<{ posted: boolean; message_type: string; coordination_error?: string | null }>(
    "/analytics/predictions/inspect",
    payload,
  );
}

export function fetchRouterStatus() {
  if (isDemoMode()) return demo.fetchRouterStatus();
  return getJson<RouterStatus>("/router/status");
}

export type AuditExport = {
  incident_information: {
    incident_id: string;
    title: string | null;
    category: string | null;
    location: string | null;
    equipment: string | null;
    created_at: string | null;
    current_status: string;
    current_risk_level: string | null;
    duplicate_count: number;
  };
  original_report: {
    source: string | null;
    message: string | null;
    received_at: string | null;
    worker_identifier: string | null;
    communication_channel: string | null;
  };
  language_processing: {
    detected_language: string | null;
    language: string | null;
    original_text: string | null;
    translated_text: string | null;
    translation_timestamp: string | null;
  };
  extracted_information: { fields: { field: string; value: string | null; confidence: number | null }[] };
  ai_decision: {
    severity: string | null;
    likelihood: string | null;
    confidence: number | null;
    detected_risks: string[];
    reasoning_summary: string | null;
    ai_recommendation: string | null;
    human_final_decision: string | null;
    override_reason: string | null;
    explanation_label: string | null;
  };
  risk_analysis: {
    score: number | null;
    base_risk_level: string | null;
    final_risk_level: string | null;
    calculation_factors: string[];
    explanation: string | null;
    rule_validation: string | null;
  };
  guidance_history: {
    guidance: string | null;
    language: string | null;
    timestamp: string | null;
    source: string | null;
    section: string | null;
    matched_text: string | null;
    line_reference: string | null;
    rule_id: string | null;
  }[];
  coordination_history: { event: string; channel: string | null; time: string | null; detail: string | null }[];
  assignment_history: {
    officer: string | null;
    previous_officer: string | null;
    assigned_at: string | null;
    reason: string | null;
  }[];
  incident_timeline: {
    time: string | null;
    event: string;
    update_type: string | null;
    message: string | null;
    created_by: string | null;
  }[];
  vision_suggestion?: {
    category: string | null;
    confidence: number | null;
    observations: string[];
    model_used: string | null;
    timestamp: string | null;
    final_decision: string | null;
    override: boolean;
    override_reason: string | null;
    changed_by: string | null;
    suggestion_only: boolean;
  } | null;
  resolution: {
    status: string | null;
    resolution_message: string | null;
    resolved_by: string | null;
    resolved_timestamp: string | null;
    evidence: string[];
    verification_status: string | null;
    human_verification: string | null;
  };
  audit_metadata: {
    export_timestamp: string;
    system_version: string;
    audit_export_version: string;
    models_used: string[];
    ai_calls: number;
    estimated_cost: string | null;
    total_processing_time: string | null;
    audit_hash: string | null;
    compliance: string[];
  };
};

export function fetchAuditExport(id: string) {
  if (isDemoMode()) return demo.fetchAuditExport(id);
  return getJson<AuditExport>(`/incidents/${encodeURIComponent(id)}/audit-export`);
}

export function fetchGuardrailStatus() {
  if (isDemoMode()) return demo.fetchGuardrailStatus();
  return getJson<GuardrailStatus>("/guardrails/status");
}

export function fetchReviewQueue() {
  if (isDemoMode()) return demo.fetchReviewQueue();
  return getJson<{ items: ReviewQueueItem[]; total: number }>("/guardrails/review-queue");
}

export function fetchGuardrailDebug() {
  if (isDemoMode()) return demo.fetchGuardrailDebug();
  return getJson<GuardrailDebugEvent[]>("/guardrails/debug");
}

export function fetchGuardrailConfig() {
  if (isDemoMode()) return demo.fetchGuardrailConfig();
  return getJson<GuardrailConfigView>("/guardrails/config");
}

export function fetchComplianceExport() {
  if (isDemoMode()) return demo.fetchComplianceExport();
  return getJson<GuardrailComplianceExport>("/guardrails/compliance-export");
}

export type TelegramBotStatus = {
  connected: boolean;
  polling_active: boolean;
  last_message_at: string | null;
  last_message: string | null;
  errors: number;
  messages_today: number;
  active_sessions: number;
  voice_reports: number;
  image_reports: number;
  emergency_reports: number;
  text_reports: number;
  message_types: Record<string, number>;
  language_distribution: Record<string, number>;
};

export function fetchTelegramHealth() {
  if (isDemoMode()) return demo.fetchTelegramHealth();
  return getJson<TelegramBotStatus>("/telegram/health");
}
