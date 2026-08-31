import type { AnalyticsSummary, IncidentSummary, RecurringHazard, RouterStatus } from "@ds/types";

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
  const response = await fetch(path);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
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
