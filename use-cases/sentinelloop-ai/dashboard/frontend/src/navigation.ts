export const NAV_GROUPS = [
  {
    label: "Operations",
    links: [
      { to: "/", label: "Dashboard", icon: "dashboard" as const },
      { to: "/emergency", label: "Emergency Command Center", icon: "emergency" as const },
      { to: "/handover/history", label: "Shift Handover History", icon: "clock" as const },
      { to: "/incidents", label: "Incident Management", icon: "incidents" as const },
      { to: "/follow-up", label: "Follow-up", icon: "followup" as const },
      { to: "/evidence", label: "Evidence Review", icon: "evidence" as const },
    ],
  },
  {
    label: "Intelligence",
    links: [
      { to: "/analytics", label: "Analytics", icon: "analytics" as const },
      { to: "/forecast/cnc-area__electrical", label: "Risk Forecast", icon: "forecast" as const },
      { to: "/reports", label: "Reports", icon: "reports" as const },
      { to: "/knowledge", label: "Knowledge Base", icon: "knowledge" as const },
    ],
  },
  {
    label: "Coordination",
    links: [
      { to: "/coordination", label: "Slack Coordination", icon: "slack" as const },
      { to: "/duplicates", label: "Duplicate Detection", icon: "duplicates" as const },
      { to: "/telegram", label: "Telegram Bot", icon: "telegram" as const },
    ],
  },
  {
    label: "People",
    links: [
      { to: "/officers", label: "Officers", icon: "officers" as const },
      { to: "/people", label: "User Management", icon: "people" as const },
    ],
  },
  {
    label: "Safety",
    links: [
      { to: "/safety", label: "AI Safety Center", icon: "safety" as const },
      { to: "/safety/review", label: "Review Required", icon: "review" as const },
      { to: "/notifications", label: "Alerts", icon: "alerts" as const },
      { to: "/settings", label: "Settings", icon: "settings" as const },
    ],
  },
] as const;

export const ROUTE_CRUMBS: { prefix: string; label: string; to?: string }[] = [
  { prefix: "/", label: "Dashboard", to: "/" },
  { prefix: "/emergency/history", label: "Emergency Response History", to: "/emergency/history" },
  { prefix: "/emergency", label: "Emergency Command Center", to: "/emergency" },
  { prefix: "/handover/history", label: "Shift Handover History", to: "/handover/history" },
  { prefix: "/incidents/", label: "Investigation", to: "/incidents" },
  { prefix: "/incidents", label: "Incidents", to: "/incidents" },
  { prefix: "/follow-up", label: "Follow-up", to: "/follow-up" },
  { prefix: "/evidence", label: "Evidence", to: "/evidence" },
  { prefix: "/analytics", label: "Analytics", to: "/analytics" },
  { prefix: "/forecast", label: "Predictions", to: "/analytics" },
  { prefix: "/reports", label: "Reports", to: "/reports" },
  { prefix: "/knowledge", label: "Knowledge", to: "/knowledge" },
  { prefix: "/coordination", label: "Teams", to: "/coordination" },
  { prefix: "/duplicates", label: "Duplicates", to: "/duplicates" },
  { prefix: "/telegram", label: "Telegram Bot", to: "/telegram" },
  { prefix: "/officers", label: "Teams", to: "/officers" },
  { prefix: "/people", label: "People", to: "/people" },
  { prefix: "/safety/review", label: "Review", to: "/safety/review" },
  { prefix: "/safety/debug", label: "Guardrail Debug", to: "/safety/debug" },
  { prefix: "/safety", label: "Safety Center", to: "/safety" },
  { prefix: "/notifications", label: "Notifications", to: "/notifications" },
  { prefix: "/settings", label: "Settings", to: "/settings" },
  { prefix: "/design-system", label: "Design System", to: "/design-system" },
];

export function crumbForPath(pathname: string) {
  return ROUTE_CRUMBS.find((item) => (item.prefix === "/" ? pathname === "/" : pathname.startsWith(item.prefix)));
}
