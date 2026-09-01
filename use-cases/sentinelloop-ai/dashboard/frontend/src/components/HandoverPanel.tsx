import { Link } from "react-router-dom";

import { Button, Card, Panel } from "@ds/index";

import type { HandoverRecord } from "../api/client";

type Props = {
  latest: HandoverRecord | null;
  generating?: boolean;
  note?: string | null;
  onGenerate?: () => void;
};

function minutesAgo(value: string | null | undefined) {
  if (!value) return "just now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const mins = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins === 1) return "1 minute ago";
  if (mins < 60) return `${mins} minutes ago`;
  return date.toLocaleString();
}

export function HandoverPanel({ latest, generating = false, note, onGenerate }: Props) {
  const shift = latest?.shift_label || "Evening Shift";
  return (
    <Panel title="Safety Shift Handover Panel" style={{ marginBottom: 24 }}>
      <div className="ds-handover-hero">
        <div>
          <p className="ds-metric__label">Latest Handover</p>
          <h3 className="ds-page-title" style={{ marginBottom: 4 }}>
            {shift}
          </h3>
          <p className="ds-mono">Generated: {latest ? minutesAgo(latest.generated_at) : "Not generated yet"}</p>
        </div>
        <Button variant="primary" onClick={onGenerate} disabled={generating} data-testid="generate-handover">
          {generating ? "Generating…" : "Generate Shift Handover"}
        </Button>
      </div>
      {note ? (
        <p className="ds-empty" role="status">
          {note}
        </p>
      ) : null}
      <div className="ds-grid ds-grid--metrics" style={{ marginTop: 16 }}>
        <Card className="ds-handover-card" variant="analytics-card">
          <p className="ds-metric__label">New Incidents</p>
          <p className="ds-metric__value">{latest?.new_incidents ?? 0}</p>
        </Card>
        <Card className="ds-handover-card" variant="analytics-card">
          <p className="ds-metric__label">Open</p>
          <p className="ds-metric__value">{latest?.open_incident_count ?? 0}</p>
        </Card>
        <Card className="ds-handover-card" variant="analytics-card">
          <p className="ds-metric__label">Critical</p>
          <p className="ds-metric__value">{latest?.critical_open_count ?? 0}</p>
        </Card>
        <Card className="ds-handover-card" variant="analytics-card">
          <p className="ds-metric__label">Review Needed</p>
          <p className="ds-metric__value">{latest?.human_review_required ?? 0}</p>
        </Card>
      </div>
      <h3 style={{ marginTop: 20 }}>Top Safety Concerns</h3>
      {(latest?.top_risks || []).length === 0 ? (
        <p className="ds-empty">No open high-priority concerns in the latest briefing.</p>
      ) : (
        <ul className="ds-handover-risks">
          {(latest?.top_risks || []).map((item) => (
            <li key={`${item.location}-${item.category}`}>
              <span>{item.risk === "Critical" || item.risk === "CRITICAL" ? "🔴" : "🟠"}</span>
              <div>
                <strong>{item.location}</strong>
                <p>
                  {item.category} · {item.risk}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
      {latest?.summary_text ? <pre className="ds-handover-summary">{latest.summary_text}</pre> : null}
      <p style={{ marginTop: 12 }}>
        <Link to="/handover/history">Open Shift Handover History</Link>
      </p>
    </Panel>
  );
}
