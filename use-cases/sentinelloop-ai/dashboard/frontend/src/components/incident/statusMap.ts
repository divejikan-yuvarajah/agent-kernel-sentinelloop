import { normalizeStatus } from "@ds/colors";

export type LiveStatus =
  | "New"
  | "Validating"
  | "Assessed"
  | "Assigned"
  | "Accepted"
  | "In Progress"
  | "Awaiting Verification"
  | "Resolved"
  | "Closed";

export type StatusTone = "danger" | "attention" | "progress" | "verified";

const STATUS_LABELS: Record<string, LiveStatus> = {
  OPEN: "New",
  NEW: "New",
  REPORTED: "New",
  VALIDATING: "Validating",
  ASSESSING: "Validating",
  ASSESSED: "Assessed",
  ASSIGNED: "Assigned",
  ACCEPTED: "Accepted",
  INVESTIGATING: "In Progress",
  IN_PROGRESS: "In Progress",
  "IN PROGRESS": "In Progress",
  AWAITING_VERIFICATION: "Awaiting Verification",
  "AWAITING VERIFICATION": "Awaiting Verification",
  VERIFIED: "Awaiting Verification",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

export function liveStatusLabel(status: string): LiveStatus {
  const key = status.trim().toUpperCase().replace(/_/g, " ");
  return STATUS_LABELS[key] ?? STATUS_LABELS[status.trim().toUpperCase()] ?? "New";
}

export function liveStatusTone(status: string): StatusTone {
  const label = liveStatusLabel(status);
  if (label === "Resolved" || label === "Closed") return "verified";
  if (label === "Awaiting Verification" || label === "Validating") return "attention";
  if (label === "New") return "danger";
  return "progress";
}

export function commandStatusKey(status: string) {
  return normalizeStatus(status);
}

export function primaryActionForStatus(status: string): { label: string; hint: string } {
  const label = liveStatusLabel(status);
  if (label === "New" || label === "Assessed") {
    return { label: "Assign Team", hint: "Route the case to the responsible crew in Slack." };
  }
  if (label === "Assigned") {
    return { label: "Accept Incident", hint: "Officer acceptance is recorded on the Slack thread." };
  }
  if (label === "Awaiting Verification") {
    return { label: "Verify Evidence", hint: "Confirm resolution evidence before closing." };
  }
  if (label === "Resolved") {
    return { label: "Close Incident", hint: "High and Critical cases require human confirmation." };
  }
  return { label: "Update Status", hint: "Continue the response from Slack coordination." };
}
