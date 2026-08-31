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
  assigned_team?: string | null;
  reporter_name?: string | null;
  source?: string | null;
  location_verified?: boolean;
  qr_equipment?: string | null;
  safety_status?: string | null;
  is_anonymous?: boolean;
  input_channel?: string | null;
  language?: string | null;
  message_type?: string | null;
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
  imageSrc?: string | null;
};

export type PredictionItem = {
  location: string;
  category: string;
  reason: string;
  recommendation: string;
  trend: string;
  incident_count: number;
  frequency_score: number;
  risk_level?: string | null;
  reason_factors: string[];
  weekly_counts: number[];
  generated_by: string;
  confidence?: number | null;
  prediction_id?: string | null;
  location_hotspot?: boolean;
  days_since_last?: number;
  span_days?: number;
  timeline: { date: string; label: string }[];
};

export type PredictionHeatmapCell = {
  location: string;
  risk: string;
  marker: string;
  active: number;
  predicted: boolean;
  electrical_images?: number;
  machine_images?: number;
  chemical_images?: number;
  other_images?: number;
};

export type PredictionsResponse = {
  generated_at: string;
  last_updated: string;
  prediction_count: number;
  predictions: PredictionItem[];
  heatmap: PredictionHeatmapCell[];
  analytics: {
    predicted_risk_zones: number;
    resolved_future_risks: number;
    inspections_triggered: number;
    prevented_recurrences: number;
  };
  weekly_counts: number[];
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
  imageSrc?: string | null;
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
  reports_by_channel?: { channel: string; count: number; percentage: number }[];
  telegram_message_types?: Record<string, number>;
  telegram_languages?: Record<string, number>;
  monthly_trend?: { label: string; value: number }[];
  category_share?: { label: string; percent: number }[];
  resolved_this_month?: number;
  ai_detection_accuracy?: string;
  worker_languages?: Record<string, number>;
  anonymous_reports?: number;
  average_detection?: string;
  average_assignment?: string;
  vision_analytics?: {
    images_analyzed: number;
    high_confidence_detections: number;
    human_overrides: number;
    average_confidence: number;
    confidence_distribution: Record<string, number>;
    hazard_detection_by_image: { label: string; percent: number; count: number }[];
    model_usage: Record<string, number>;
    location_heatmap: {
      location: string;
      risk: string | null;
      electrical_images: number;
      machine_images: number;
      chemical_images: number;
      other_images: number;
      total_images: number;
    }[];
  };
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
  kind: "image" | "file" | "voice";
  stage?: string | null;
  uploaded_by?: string | null;
  channel?: string | null;
  imageSrc?: string | null;
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

export type SafetyActiveCard = {
  name: string;
  active: boolean;
  spec_rule?: string | null;
};

export type GuardrailMetrics = {
  total_validations: number;
  passed: number;
  blocked: number;
  warnings: number;
};

export type SafetyViolationCounts = {
  guidance_hallucinations: number;
  privacy_attempts: number;
  blocked_closures: number;
  budget_blocks: number;
};

export type SafetyComplianceCharts = {
  guidance_validation_success_rate: number;
  incidents_requiring_human_review: number;
  blocked_ai_outputs: number;
  anonymous_reports_percentage: number;
  average_ai_cost_per_incident: number;
};

export type GuardrailStatus = {
  cards: SafetyActiveCard[];
  metrics: GuardrailMetrics;
  violations: SafetyViolationCounts;
  charts: SafetyComplianceCharts;
  budget_ceiling_usd: number | null;
  budget_spent_usd: number;
};

export type GuidanceVerification = {
  knowledge_base_file: string | null;
  supported_lines: string | null;
  hallucination_check: string | null;
  generated_guidance?: string | null;
};

export type IncidentSafetyPanel = {
  incident_id: string;
  safety_status: string;
  risk_level: string | null;
  human_review: string;
  guidance: string;
  closure: string;
  auto_close_disabled: boolean;
  guidance_verification: GuidanceVerification;
  timeline: { timestamp: string | null; title: string; detail: string | null }[];
  assigned_reviewer: string | null;
};

export type ReviewQueueItem = {
  incident_id: string;
  risk_level: string | null;
  reason: string;
  assigned_reviewer: string | null;
  waiting_time: string | null;
  status: string | null;
  actions: string[];
  actions_enabled: boolean;
  action_hint: string | null;
};

export type GuardrailDebugEvent = {
  timestamp: string | null;
  guardrail: string;
  event: string;
  input_summary: string | null;
  validation_result: string;
  agent_output: string | null;
  rule_violated: string | null;
  decision: string | null;
  incident_id: string | null;
  violations: string[];
};

export type GuardrailConfigView = {
  ai_budget_ceiling: string | null;
  guidance_validation_strictness: string | null;
  anonymous_data_policy: string | null;
  closure_rules: string | null;
  max_text_length: number | null;
  max_attachment_bytes: number | null;
  writable: boolean;
};

export type GuardrailComplianceExport = {
  generated_at: string;
  validation_history: Record<string, unknown>[];
  violations: SafetyViolationCounts;
  human_approvals: number;
  incident_count: number;
  ai_spend_usd: number;
  budget_ceiling_usd: number | null;
  audit_note: string | null;
};
