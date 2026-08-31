/** Compatibility re-exports from the Horizon demo dataset. Prefer `@/data/demoData`. */

import type { ActivityEvent, AnalyticsPoint, EvidenceItem, Incident, Officer, RiskAssessment, TimelineEvent } from "@ds/types";
import { normalizeRisk } from "@ds/colors";

import { activity as horizonActivity, evidenceRecords, incidents as horizonIncidents, monthlyTrend, users } from "./demoData";

export const incidents: Incident[] = horizonIncidents.slice(0, 4).map((row) => ({
  id: row.incident_id,
  title: row.title,
  location: row.location,
  reportedAt: row.created_at.slice(11, 19),
  riskLevel: normalizeRisk(row.risk_level),
  riskScore: row.risk_score,
  status: row.status,
  assignedOfficer: row.assigned_officer,
}));

export const timeline: Record<string, TimelineEvent[]> = {
  [horizonIncidents[0].incident_id]: [
    { timestamp: "14:50", title: "Worker message received", detail: horizonIncidents[0].original_text },
    { timestamp: "14:51", title: "Language detected: Sinhala", detail: horizonIncidents[0].translated_text },
    { timestamp: "14:52", title: "Risk calculated", detail: horizonIncidents[0].risk_explanation },
    { timestamp: "14:54", title: "Slack notification created", detail: horizonIncidents[0].assigned_team },
  ],
};

export const assessments: Record<string, RiskAssessment> = {
  [horizonIncidents[0].incident_id]: {
    level: normalizeRisk(horizonIncidents[0].risk_level),
    score: horizonIncidents[0].risk_score,
    confidence: 95,
    hazards: [horizonIncidents[0].category, horizonIncidents[0].equipment || "", `${horizonIncidents[0].people_exposed} people exposed`],
    reasoning: horizonIncidents[0].risk_explanation,
  },
};

export const evidence: EvidenceItem[] = evidenceRecords.map((item) => ({
  id: item.id,
  label: item.label,
  source: item.source,
  timestamp: item.date,
  kind: item.kind,
  stage: item.stage,
}));

export const activity: ActivityEvent[] = horizonActivity.map((item) => ({
  timestamp: item.timestamp,
  kind: item.kind,
  summary: item.summary,
  incident_id: item.incident_id,
}));

export const officers: Officer[] = users
  .filter((user) => user.role !== "Worker")
  .slice(0, 4)
  .map((user, index) => ({
    id: user.id,
    name: user.name,
    team: user.team,
    load: 3 - index,
    status: "INVESTIGATING",
  }));

export const incidentsOverTime: AnalyticsPoint[] = monthlyTrend;

export const riskDistribution = [
  { level: "LOW" as const, count: 91 },
  { level: "MEDIUM" as const, count: 96 },
  { level: "HIGH" as const, count: 48 },
  { level: "CRITICAL" as const, count: 12 },
];
