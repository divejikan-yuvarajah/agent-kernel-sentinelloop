import { normalizeRisk } from "../colors";
import type { IncidentSummary } from "../types";
import { Badge } from "./Badge";
import { Card } from "./Card";
import { ChannelBadge } from "./ChannelBadge";
import { RiskIndicator } from "./RiskIndicator";
import { StatusIndicator } from "./StatusIndicator";

type Props = {
  incident: IncidentSummary;
  onOpen?: (id: string) => void;
  loading?: boolean;
  imageSrc?: string | null;
  pulse?: boolean;
};

function cardState(incident: IncidentSummary) {
  const status = incident.status.toUpperCase().replace(/\s+/g, "_");
  if (status === "RESOLVED" || status === "CLOSED") return "resolved";
  if ((incident.risk_level || "").toUpperCase() === "CRITICAL") return "critical";
  return "active";
}

export function IncidentOverviewCard({ incident, onOpen, loading = false, imageSrc = null, pulse = false }: Props) {
  if (loading) {
    return <Card variant="incident-card" loading aria-hidden="true" />;
  }
  const state = cardState(incident);
  const risk = normalizeRisk(incident.risk_level ?? "MEDIUM");
  const showDuplicate = incident.duplicate_count > 1;
  return (
    <Card
      variant="incident-card"
      riskLevel={incident.risk_level ?? "MEDIUM"}
      role="button"
      className={`ds-card--incident-${state}${pulse ? ` ds-card--pulse ds-card--pulse-${risk}` : ""}`}
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
            <ChannelBadge channel={incident.source === "QR_TAGGED" ? "qr" : incident.input_channel} />
          ) : null}
          {incident.safety_status ? (
            <Badge title="Responsible AI safety status">{incident.safety_status}</Badge>
          ) : null}
        </header>
        <div className="ds-incident-card__body">
          <dl className="ds-incident-card__meta">
            <div>
              <dt>Location</dt>
              <dd>{incident.location ?? "Location unknown"}</dd>
            </div>
            <div>
              <dt>Risk</dt>
              <dd>
                <RiskIndicator level={incident.risk_level ?? "MEDIUM"} />
                <span className={`ds-badge ds-badge--risk-${normalizeRisk(incident.risk_level ?? "MEDIUM")}`}>
                  {normalizeRisk(incident.risk_level ?? "MEDIUM")}
                </span>
              </dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <StatusIndicator status={incident.status} />
              </dd>
            </div>
          </dl>
          {incident.location_verified ? (
            <p className="ds-verified ds-mono" title="Location verified by QR tag">
              Location verified
              {incident.qr_equipment ? ` · ${incident.qr_equipment}` : ""}
            </p>
          ) : null}
          <div className="ds-meta-row" style={{ marginTop: 8 }}>
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
