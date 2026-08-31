import type { ActivityEvent, AnalyticsPoint, EvidenceItem, Incident, Officer, RiskAssessment, TimelineEvent } from "@ds/types";
import type { RiskLevel } from "@ds/colors";

export const incidents: Incident[] = [
  {
    id: "INC-0042",
    title: "Electrical panel sparking",
    location: "Electrical Room / QR Bay 2",
    reportedAt: "14:12:08",
    riskLevel: "CRITICAL",
    riskScore: 20,
    status: "IN_PROGRESS",
    assignedOfficer: "N. Fernando",
    coordinates: "6.9271, 79.8612",
  },
  {
    id: "INC-0041",
    title: "Oil leak near packing line",
    location: "Packing Area 3",
    reportedAt: "13:48:21",
    riskLevel: "HIGH",
    riskScore: 12,
    status: "ASSIGNED",
    assignedOfficer: "S. Jayasuriya",
  },
  {
    id: "INC-0039",
    title: "Wet floor at loading bay",
    location: "Loading Bay A",
    reportedAt: "11:02:44",
    riskLevel: "MEDIUM",
    riskScore: 9,
    status: "AWAITING_VERIFICATION",
    assignedOfficer: "M. Silva",
  },
  {
    id: "INC-0036",
    title: "Missing PPE on machine 4",
    location: "Machine Hall",
    reportedAt: "09:17:03",
    riskLevel: "LOW",
    riskScore: 4,
    status: "RESOLVED",
    assignedOfficer: "K. Bandara",
  },
];

export const timeline: Record<string, TimelineEvent[]> = {
  "INC-0042": [
    { timestamp: "14:12:08", title: "Report received", detail: "WhatsApp worker report, Sinhala." },
    { timestamp: "14:12:11", title: "AI classification", detail: "Hazard category electrical." },
    { timestamp: "14:12:13", title: "Risk assessment", detail: "Critical override: active electrical hazard." },
    { timestamp: "14:12:18", title: "Officer assignment", detail: "Electrical Maintenance · N. Fernando." },
    { timestamp: "14:31:02", title: "Resolution", detail: "Pending worker verification." },
  ],
};

export const assessments: Record<string, RiskAssessment> = {
  "INC-0042": {
    level: "CRITICAL",
    score: 20,
    confidence: 92,
    hazards: ["Live electrical panel", "Active sparking", "People exposed: 6"],
    reasoning: "Active electrical hazard with injury unknown and six people in the area. Deterministic matrix plus override produced Critical.",
  },
};

export const evidence: EvidenceItem[] = [
  { id: "EV-118", label: "Worker photo — panel", source: "WhatsApp worker", timestamp: "14:12:09", kind: "image" },
  { id: "EV-121", label: "Remediation note", source: "Slack officer", timestamp: "14:28:40", kind: "file" },
];

export const activity: ActivityEvent[] = [
  { timestamp: "14:31:02", kind: "Officer update", summary: "INC-0042 isolation in progress." },
  { timestamp: "14:12:18", kind: "System event", summary: "Slack card posted to Electrical Maintenance." },
  { timestamp: "14:12:08", kind: "New report", summary: "INC-0042 opened from WhatsApp." },
  { timestamp: "13:48:21", kind: "New report", summary: "INC-0041 oil leak, Packing Area 3." },
];

export const officers: Officer[] = [
  { id: "OFF-01", name: "N. Fernando", team: "Electrical Maintenance", load: 2, status: "INVESTIGATING" },
  { id: "OFF-02", name: "S. Jayasuriya", team: "Facilities", load: 1, status: "OPEN" },
  { id: "OFF-03", name: "M. Silva", team: "Safety Supervisor", load: 1, status: "VERIFIED" },
];

export const incidentsOverTime: AnalyticsPoint[] = [
  { label: "Mon", value: 4 },
  { label: "Tue", value: 6 },
  { label: "Wed", value: 3 },
  { label: "Thu", value: 8 },
  { label: "Fri", value: 5 },
  { label: "Sat", value: 2 },
  { label: "Sun", value: 1 },
];

export const riskDistribution: { level: RiskLevel; count: number }[] = [
  { level: "LOW", count: 6 },
  { level: "MEDIUM", count: 9 },
  { level: "HIGH", count: 5 },
  { level: "CRITICAL", count: 2 },
];
