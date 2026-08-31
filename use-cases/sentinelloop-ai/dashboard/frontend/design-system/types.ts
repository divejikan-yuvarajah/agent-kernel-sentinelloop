import type { RiskLevel } from "./colors";

export type { RiskLevel };

export type Incident = {
  id: string;
  title: string;
  location: string;
  reportedAt: string;
  riskLevel: RiskLevel;
  riskScore: number;
  status: string;
  assignedOfficer: string;
  coordinates?: string;
};

export type IncidentSummary = {
  incident_id: string;
  title: string | null;
  category: string | null;
  location: string | null;
  status: string;
  risk_level: string | null;
  risk_score: number | null;
  created_at: string | null;
  updated_at: string | null;
  elapsed_time: string | null;
  assigned_officer: string | null;
  duplicate_count: number;
  loop_stage: string | null;
  source?: string | null;
  location_verified?: boolean;
  qr_equipment?: string | null;
};

export type LoopStage = {
  stage: string;
  label: string;
  count: number;
  percentage: number;
};

export type ModelCall = {
  timestamp: string | null;
  model: string | null;
  model_role: string | null;
  agent_role: string | null;
  tier: string | null;
  latency_s: number | null;
  token_usage: {
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
    total_tokens?: number | null;
  };
  cost_usd: number;
};

export type RouterStatus = {
  budget: {
    budget_limit: number | null;
    spent: number;
    remaining: number | null;
    usage_percentage: number | null;
  };
  recent_calls: ModelCall[];
  request_count: number;
  paid_call_count: number;
  ledger_available: boolean;
};

export type RecurringHazard = {
  category: string;
  location: string;
  count: number;
  period: string;
  severity: string;
  recommendation: string;
  recurrence_percentage: number;
  trend_direction: "up" | "down" | "stable";
  first_seen: string | null;
  last_seen: string | null;
};

export type ActivityEvent = {
  timestamp: string;
  kind: string;
  summary: string;
  incident_id?: string | null;
};

export type QrLocationStat = {
  location: string;
  equipment: string | null;
  count: number;
  risk_score: number | null;
  insight: string | null;
};

export type RepeatedHazardStat = {
  label: string;
  location: string | null;
  count: number;
  insight: string | null;
};

export type AnalyticsSummary = {
  total_incidents: number;
  open_incidents: number;
  critical_incidents: number;
  resolved_today: number;
  avg_response_time: string | null;
  incidents_last_24_hours: number;
  incidents_last_7_days: number;
  incidents_by_risk_level: Record<string, number>;
  incidents_by_category: Record<string, number>;
  average_resolution_time: string | null;
  fastest_response_time: string | null;
  slowest_response_time: string | null;
  loop_stages: LoopStage[];
  recent_activity: ActivityEvent[];
  qr_tagged_incidents?: number;
  top_qr_locations?: QrLocationStat[];
  most_repeated_hazards?: RepeatedHazardStat[];
  repeated_hazard_locations?: RepeatedHazardStat[];
  duplicate_detection_stats?: Record<string, number>;
};

export type TimelineEvent = {
  timestamp: string;
  title: string;
  detail?: string;
};

export type RiskAssessment = {
  level: RiskLevel;
  score: number;
  confidence: number;
  hazards: string[];
  reasoning: string;
};

export type EvidenceItem = {
  id: string;
  label: string;
  source: string;
  timestamp: string;
  kind: "image" | "file";
};

export type AnalyticsPoint = {
  label: string;
  value: number;
};

export type Officer = {
  id: string;
  name: string;
  team: string;
  load: number;
  status: string;
};
