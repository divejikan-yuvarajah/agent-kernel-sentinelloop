import type { ActivityEvent } from "../types";
import { Card } from "./Card";

type Props = {
  events: ActivityEvent[];
  loading?: boolean;
};

const KIND_FROM_TYPE: Record<string, string> = {
  incident_created: "New report",
  intake_completed: "AI intake",
  risk_assessed: "Risk assessed",
  status_transition: "Status",
  whatsapp_inbound: "Worker report",
  whatsapp_outbound: "Guidance sent",
  guidance_sent: "Guidance sent",
  guidance_generated: "Guidance sent",
  guidance_fallback: "Guardrail blocked",
  slack_coordination_completed: "Officer action",
  incident_assigned: "Officer action",
  incident_accepted: "Officer action",
  duplicate_report_linked: "Duplicate report",
  duplicate_threshold_reached: "Priority increase",
  incident_resolved: "Resolved",
  incident_closed: "Closed",
  incident_reopened: "Reopened",
  worker_verification_confirmed: "Worker confirmed",
  supervisor_review: "Supervisor review",
  evidence_uploaded: "Evidence",
  evidence_added: "Evidence",
};

function formatStamp(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function humanize(event: ActivityEvent): { kind: string; summary: string } {
  const raw = (event.summary || "").trim();
  if (!raw.startsWith("{")) {
    return { kind: event.kind, summary: event.summary };
  }
  try {
    const parsed = JSON.parse(raw) as {
      update_type?: string;
      message?: string;
      previous_status?: string | null;
      new_status?: string | null;
    };
    const type = parsed.update_type || "";
    const kind = KIND_FROM_TYPE[type] || (event.kind !== "System event" ? event.kind : type.replace(/_/g, " "));
    const summary =
      parsed.message ||
      (parsed.previous_status && parsed.new_status ? `${parsed.previous_status} → ${parsed.new_status}` : "Incident update");
    return { kind: kind || "Update", summary };
  } catch {
    return { kind: event.kind === "System event" ? "Update" : event.kind, summary: "Incident update" };
  }
}

export function ActivityFeed({ events, loading = false }: Props) {
  if (loading) {
    return <Card variant="activity-card" loading />;
  }
  if (events.length === 0) {
    return <Card variant="activity-card" empty emptyMessage="No live activity." />;
  }
  return (
    <Card variant="activity-card">
      <ul className="ds-feed">
        {events.map((event, index) => {
          const item = humanize(event);
          return (
            <li key={`${event.timestamp}-${event.kind}-${index}`} className="ds-feed__item">
              <time className="ds-feed__time" dateTime={event.timestamp}>
                {formatStamp(event.timestamp)}
              </time>
              <div className="ds-feed__body">
                <strong>{item.kind}</strong>
                {event.incident_id ? <span className="ds-feed__ref">{event.incident_id}</span> : null}
                <p className="ds-feed__summary">{item.summary}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
