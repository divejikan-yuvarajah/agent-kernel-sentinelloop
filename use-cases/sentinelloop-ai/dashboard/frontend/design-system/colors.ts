export const colors = {
  ink: "#1C2024",
  panel: "#262B31",
  chalk: "#F2F0EA",
  signalAmber: "#E8A33D",
  emberOrange: "#C9642E",
  hazardRed: "#D64545",
  verifiedTeal: "#3FA796",
  chalkMuted: "#B7B5AE",
  border: "#3A4047",
} as const;

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type IncidentStatusKey = "OPEN" | "INVESTIGATING" | "VERIFIED" | "RESOLVED";

export const riskColors: Record<RiskLevel, string> = {
  LOW: colors.verifiedTeal,
  MEDIUM: colors.signalAmber,
  HIGH: colors.emberOrange,
  CRITICAL: colors.hazardRed,
};

export const statusColors: Record<IncidentStatusKey, string> = {
  OPEN: colors.hazardRed,
  INVESTIGATING: colors.signalAmber,
  VERIFIED: colors.verifiedTeal,
  RESOLVED: colors.verifiedTeal,
};

/** Map SentinelLoop lifecycle strings onto the four command-center status keys. */
export const lifecycleToStatus: Record<string, IncidentStatusKey> = {
  OPEN: "OPEN",
  NEW: "OPEN",
  REPORTED: "OPEN",
  INVESTIGATING: "INVESTIGATING",
  VALIDATING: "INVESTIGATING",
  ASSESSING: "INVESTIGATING",
  ASSESSED: "INVESTIGATING",
  ASSIGNED: "INVESTIGATING",
  ACCEPTED: "INVESTIGATING",
  "IN PROGRESS": "INVESTIGATING",
  IN_PROGRESS: "INVESTIGATING",
  VERIFIED: "VERIFIED",
  "AWAITING VERIFICATION": "VERIFIED",
  AWAITING_VERIFICATION: "VERIFIED",
  RESOLVED: "RESOLVED",
  CLOSED: "RESOLVED",
};

export function normalizeStatus(status: string): IncidentStatusKey {
  const key = status.trim().toUpperCase().replace(/_/g, " ");
  return lifecycleToStatus[key] ?? lifecycleToStatus[status.trim().toUpperCase()] ?? "OPEN";
}

export function normalizeRisk(risk: string): RiskLevel {
  const key = risk.trim().toUpperCase();
  if (key === "LOW" || key === "MEDIUM" || key === "HIGH" || key === "CRITICAL") {
    return key;
  }
  return "MEDIUM";
}
