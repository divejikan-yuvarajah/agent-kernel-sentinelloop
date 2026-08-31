import type { IncidentSummary } from "../types";
import { Badge } from "./Badge";
import { Card } from "./Card";
import { StatusIndicator } from "./StatusIndicator";

type Props = {
  incident: IncidentSummary;
  onOpen?: (id: string) => void;
  loading?: boolean;
  imageSrc?: string | null;
};

function cardState(incident: IncidentSummary) {
  const status = incident.status.toUpperCase().replace(/\s+/g, "_");
  if (status === "RESOLVED" || status === "CLOSED") return "resolved";
  if ((incident.risk_level || "").toUpperCase() === "CRITICAL") return "critical";
  return "active";
}

export function IncidentOverviewCard({ incident, onOpen, loading = false, imageSrc = null }: Props) {
  if (loading) {
    return <Card variant="incident-card" loading aria-hidden="true" />;
  }
  const state = cardState(incident);
  const showDuplicate = incident.duplicate_count > 1;
  return (
    <Card
      variant="incident-card"
      riskLevel={incident.risk_level ?? "MEDIUM"}
      role="button"
      className={`ds-card--incident-${state}`}
      onClick={() => onOpen?.(incident.incident_id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen?.(incident.incident_id);
        }
      }}
      aria-label={`Incident ${incident.incident_id}, ${incident.category ?? "uncategorized"}, ${incident.status}`}
    >
      <div className="ds-incident-card">
        {imageSrc ? (
          <div className="ds-incident-card__photo">
            <img src={imageSrc} alt="" loading="lazy" />
          </div>
        ) : null}
        <header className="ds-incident-card__head">
          <p className="ds-mono" style={{ margin: 0, fontSize: "var(--font-size-xs)" }}>
            {incident.incident_id}
          </p>
          <p className="ds-mono" style={{ margin: 0, fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
            {incident.category ?? "Uncategorized"}
          </p>
          {showDuplicate ? (
            <Badge title="Multiple workers reported this same hazard">{incident.duplicate_count} REPORTS</Badge>
          ) : null}
          {incident.source === "QR_TAGGED" ? (
            <Badge title="Location verified by QR scan">QR Tagged</Badge>
          ) : null}
          {incident.input_channel ? (
            <Badge title={`Reported via ${incident.input_channel}`}>
              {incident.input_channel === "telegram"
                ? "📱 Telegram"
                : incident.input_channel === "whatsapp"
                  ? "🟢 WhatsApp"
                  : incident.input_channel === "slack"
                    ? "💬 Slack"
                    : incident.input_channel === "email"
                      ? "📧 Email"
                      : incident.input_channel}
            </Badge>
          ) : null}
          {incident.safety_status ? (
            <Badge title="Responsible AI safety status">{incident.safety_status}</Badge>
          ) : null}
        </header>
        <div className="ds-incident-card__body">
          <p style={{ margin: 0 }}>{incident.location ?? "Location unknown"}</p>
          {incident.location_verified ? (
            <p className="ds-verified ds-mono" title="Location verified by QR tag">
              Location verified
              {incident.qr_equipment ? ` · ${incident.qr_equipment}` : ""}
            </p>
          ) : null}
          <div className="ds-meta-row" style={{ marginTop: 8 }}>
            <StatusIndicator status={incident.status} />
            <span className="ds-mono">{incident.elapsed_time ?? "—"}</span>
          </div>
        </div>
        <footer className="ds-incident-card__foot">
          <span className="ds-mono">Risk {incident.risk_score ?? "—"}</span>
          <span>{incident.assigned_officer ?? "Unassigned"}</span>
        </footer>
      </div>
    </Card>
  );
}
