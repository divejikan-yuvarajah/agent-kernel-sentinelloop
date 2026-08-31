import type { AnalyticsSummary, IncidentSummary, RecurringHazard, RouterStatus } from "@ds/types";

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

export function fetchIncidents(params: Record<string, string | number | undefined> = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    query.set(key, String(value));
  }
  const suffix = query.size ? `?${query.toString()}` : "";
  return getJson<IncidentListResponse>(`/incidents${suffix}`);
}

export function fetchIncident(id: string) {
  return getJson<IncidentDetail>(`/incidents/${encodeURIComponent(id)}`);
}

export function fetchAnalyticsSummary() {
  return getJson<AnalyticsSummary>("/analytics/summary");
}

export function fetchRecurring() {
  return getJson<{ items: RecurringHazard[] }>("/analytics/recurring");
}

export function fetchRouterStatus() {
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
  return getJson<AuditExport>(`/incidents/${encodeURIComponent(id)}/audit-export`);
}
