export const colors = {
  ink: "#FFFFFF",
  panel: "#FFFFFF",
  panelRaised: "#F6F1F0",
  chalk: "#1F1114",
  muted: "#7A5C5A",
  maroon: "#7C1F2E",
  maroonDeep: "#5C1620",
  verifiedTeal: "#3FA796",
  signalAmber: "#E0A83D",
  emberOrange: "#C9642E",
  hazardRed: "#E63946",
  onBrand: "#FFFFFF",
} as const;

/** @deprecated Use colors.muted */
export const chalkMuted = colors.muted;

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
