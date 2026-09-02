import type { IconName } from "@ds/index";
import type { LoopStage } from "@ds/types";

const BOT_USERNAME = (import.meta.env.VITE_TELEGRAM_BOT_USERNAME || "SentinelLoop_ReportBot").replace(/^@/, "");

export const TELEGRAM_BOT_HANDLE = `@${BOT_USERNAME}`;
export const TELEGRAM_BOT_URL = `https://t.me/${BOT_USERNAME}`;
export const GITHUB_REPO_URL = "https://github.com/divejikan-yuvarajah/agent-kernel-sentinelloop";
export const AGENT_KERNEL_URL = "https://kernel.yaala.ai";
export const DASHBOARD_PATH = "/dashboard";
export const SANDBOX_PATH = "/sandbox";

export const LANDING_TITLE = "SentinelLoop AI — Report danger in seconds";
export const LANDING_DESCRIPTION =
  "SentinelLoop AI turns a two-second Telegram message into a tracked, accountable safety response — in Sinhala, Tamil, or English.";

export const NAV_LINKS = [
  { href: "#why", label: "Why" },
  { href: "#how", label: "How it works" },
  { href: "#features", label: "Features" },
  { href: "#trust", label: "Trust" },
] as const;

export const TEAM_ZATROZ = {
  name: "Team Zatroz",
  members: ["Yuvarajah Divejikan", "Abdul Basith", "Prabhath Nishantha"],
};

export const HERO_STATS = [
  { value: "3", label: "Languages on the floor" },
  { value: "7", label: "Stages in the safety loop" },
  { value: "0", label: "AI calls on SOS path" },
];

export const LOOP_STAGES: LoopStage[] = [
  { stage: "report", label: "Report", count: 1, percentage: 14 },
  { stage: "understand", label: "Understand", count: 1, percentage: 14 },
  { stage: "assess", label: "Assess", count: 1, percentage: 14 },
  { stage: "alert", label: "Alert", count: 1, percentage: 15 },
  { stage: "act", label: "Act", count: 1, percentage: 14 },
  { stage: "verify", label: "Verify", count: 1, percentage: 14 },
  { stage: "learn", label: "Learn", count: 1, percentage: 15 },
];

export const STAGE_IDENTITY: Record<string, { title: string; body: string }> = {
  report: {
    title: "Report",
    body: "A worker sends text, a photo, or a voice note on Telegram.",
  },
  understand: {
    title: "Understand",
    body: "Intake detects language and turns the message into a structured hazard.",
  },
  assess: {
    title: "Assess",
    body: "The model estimates severity. A deterministic matrix sets the final risk level.",
  },
  alert: {
    title: "Alert",
    body: "The assigned safety team is notified in Slack with the case already opened.",
  },
  act: {
    title: "Act",
    body: "Officers respond, record what they did, and keep ownership on the case.",
  },
  verify: {
    title: "Verify",
    body: "High and Critical incidents stay open until a human confirms the floor is safe.",
  },
  learn: {
    title: "Learn",
    body: "Recurring patterns become the next inspection recommendation — not a forgotten chat.",
  },
};

export const PROBLEMS = [
  {
    icon: "knowledge" as IconName,
    title: "Language barriers",
    description:
      "Workers are often more fluent in Sinhala or Tamil than in the English typically required by formal safety forms.",
  },
  {
    icon: "incidents" as IconName,
    title: "Reporting friction",
    description:
      "Paper forms, long web forms, or “tell your supervisor” processes are too slow for something noticed in passing.",
  },
  {
    icon: "emergency" as IconName,
    title: "Near-misses get ignored",
    description:
      "An event that could have caused injury but didn’t often isn’t recorded at all, so the same hazard recurs.",
  },
  {
    icon: "people" as IconName,
    title: "No clear ownership",
    description:
      "A report dropped into a group chat or told to a supervisor verbally has no assigned owner, no deadline, and no follow-up.",
  },
];

export const HOW_IT_WORKS = [
  {
    title: "Report",
    description: "A worker sends text, a photo, or a voice note on Telegram — in Sinhala, Tamil, or English.",
  },
  {
    title: "Understood & Translated",
    description: "Intake detects language, translates when needed, and keeps the same incident session continuous.",
  },
  {
    title: "Risk Assessed",
    description: "The model estimates severity and likelihood. A deterministic safety matrix sets the final risk level.",
  },
  {
    title: "Team Alerted",
    description: "Slack notifies the assigned team so an officer can accept, reassign, or escalate.",
  },
  {
    title: "Resolved & Verified",
    description: "Evidence is uploaded. The incident stays open until a worker confirms the floor is actually safe.",
  },
];

export const FEATURES: {
  icon: IconName;
  title: string;
  description: string;
  badge?: string;
}[] = [
  {
    icon: "search",
    title: "QR reporting",
    description:
      "Scan a QR at a machine and Telegram opens pre-tagged with location and equipment; the worker only describes the hazard.",
  },
  {
    icon: "duplicates",
    title: "Duplicate merge",
    description:
      "Local text-similarity first, LLM only as a rare tiebreaker — repeated reports of the same spill collapse into one incident with auto-escalated priority.",
  },
  {
    icon: "export",
    title: "Audit export",
    description:
      "One click produces the full decision trail from raw report to resolution, in a format a safety inspector could actually use.",
  },
  {
    icon: "emergency",
    title: "Emergency bypass",
    description:
      "“SOS” / 🆘 in any supported language triggers an instant, hardcoded Critical alert with zero LLM calls in the critical path.",
    badge: "zero AI in this path",
  },
  {
    icon: "forecast",
    title: "Prediction",
    description:
      "Recurring category and location patterns surface as “recommend inspection before next shift,” turning the system from reactive to preventive.",
  },
  {
    icon: "image",
    title: "Vision triage",
    description: "A hazard photo with little or no caption still gets a category suggestion via a vision-capable model.",
  },
  {
    icon: "alerts",
    title: "Voice reporting",
    description:
      "Telegram voice notes are transcribed in the worker’s own language, with spend tracked against the same OpenRouter budget as text and vision.",
  },
  {
    icon: "clock",
    title: "Shift handover",
    description:
      "Open, critical, review, and overdue incidents are phrased into a briefing the next shift can use, then posted to the Slack Safety Channel.",
  },
  {
    icon: "incidents",
    title: "Manual dashboard entry",
    description:
      "Officers can log a phoned-in or in-person report directly — the same intake → risk → guidance → Slack pipeline as Telegram, with no shortcut rules.",
  },
  {
    icon: "alerts",
    title: "Live Safety Simulator",
    description: "Experience the complete AI safety pipeline instantly without setup.",
  },
];

export const TRUST_PILLARS = [
  {
    title: "Deterministic risk matrix",
    description:
      "The risk agent estimates severity and likelihood. calculate_risk() is a deterministic tool the agent must call — the matrix decides, the LLM only estimates the inputs.",
  },
  {
    title: "Cost-governed OpenRouter router",
    description:
      "Every LLM call is routed through a single cost-governed OpenRouter model router rather than agents calling providers directly. Spend is tracked against a configured budget ceiling.",
  },
  {
    title: "Human-in-the-loop closure",
    description:
      "High and Critical incidents require human confirmation before closing. A worker confirmation step closes the loop so nothing is marked resolved on an officer’s word alone.",
  },
];

export const SDGS = [
  { code: "3", title: "Good Health & Well-Being" },
  { code: "8", title: "Decent Work & Economic Growth" },
  { code: "9", title: "Industry, Innovation & Infrastructure" },
  { code: "10", title: "Reduced Inequalities" },
  { code: "16", title: "Peace, Justice & Strong Institutions" },
];
