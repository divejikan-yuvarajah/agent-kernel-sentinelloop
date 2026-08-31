import { Link } from "react-router-dom";

import { AppShell, Card, Panel } from "@ds/index";

import { fetchEmergencies, type EmergencyCommandCenter } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";
import { useEffect, useState } from "react";

export function EmergencyHistoryTable({ rows }: { rows: EmergencyCommandCenter["history"] }) {
  return (
    <div className="ds-table-wrap">
      <table className="ds-emergency-table">
        <thead>
          <tr>
            <th>Incident</th>
            <th>Trigger</th>
            <th>Channel</th>
            <th>Detection Time</th>
            <th>Response Time</th>
            <th>Resolution</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.incident_id}-${row.detection_time}`}>
              <td>
                <Link to={`/incidents/${row.incident_id}`}>{row.incident_id}</Link>
              </td>
              <td>{row.trigger || "—"}</td>
              <td>{row.channel || "—"}</td>
              <td className="ds-mono">{row.detection_time || "—"}</td>
              <td>{row.response_time || "—"}</td>
              <td>{row.resolution || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EmergencyPage() {
  const [demo] = useDemoMode();
  const [data, setData] = useState<EmergencyCommandCenter | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEmergencies()
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [demo]);

  const metrics = data?.metrics;
  const active = data?.active ?? [];
  const timeline = data?.timeline ?? [];
  const history = data?.history ?? [];

  return (
    <AppShell title="Emergency Command Center" operationalStatus="OPEN">
      <p className="ds-page-lead">
        Urgent worker reports bypass AI triage. Humans are notified first; enrichment follows on the same incident.
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : null}
      <div className="ds-grid ds-grid--metrics-3">
        <Card className="ds-emergency-card" variant="analytics-card">
          <p className="ds-metric__label">Emergency Alerts Today</p>
          <p className="ds-metric__value">{metrics?.emergency_alerts_today ?? 0}</p>
        </Card>
        <Card className="ds-emergency-card" variant="analytics-card">
          <p className="ds-metric__label">Average Response Time</p>
          <p className="ds-metric__value">{metrics?.average_response_time ?? "—"}</p>
        </Card>
        <Card className="ds-emergency-card" variant="analytics-card">
          <p className="ds-metric__label">Active Critical Incidents</p>
          <p className="ds-metric__value">{metrics?.active_critical_incidents ?? 0}</p>
        </Card>
      </div>
      <Panel title="Active Emergencies">
        {active.length === 0 ? (
          <p className="ds-empty">No active emergencies.</p>
        ) : (
          <div className="ds-grid ds-grid--cards">
            {active.map((item) => (
              <Card key={item.incident_id} className="ds-emergency-card" variant="incident-card" riskLevel="CRITICAL">
                <p className="ds-emergency-kicker">🚨 Active Emergency</p>
                <h3>Incident: {item.incident_id}</h3>
                <p>Location: {item.location || "Unknown"}</p>
                <p>Time: {item.time || "—"}</p>
                <p>Response: {item.response}</p>
              </Card>
            ))}
          </div>
        )}
      </Panel>
      <Panel title="Emergency Timeline" style={{ marginTop: 24 }}>
        {timeline.length === 0 ? (
          <p className="ds-empty">No emergency events in this session.</p>
        ) : (
          <ol className="ds-emergency-timeline">
            {timeline.map((item) => (
              <li key={`${item.time}-${item.event}`}>
                <time>{item.time || "—"}</time>
                <span>{item.event}</span>
              </li>
            ))}
          </ol>
        )}
      </Panel>
      <Panel title="Emergency Response History" style={{ marginTop: 24 }}>
        <p>
          <Link to="/emergency/history">Open full history</Link>
        </p>
        {history.length === 0 ? <p className="ds-empty">No emergency history.</p> : <EmergencyHistoryTable rows={history} />}
      </Panel>
    </AppShell>
  );
}
