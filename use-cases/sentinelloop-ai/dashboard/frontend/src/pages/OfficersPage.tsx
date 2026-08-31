import { useEffect, useMemo, useState } from "react";

import { AppShell, Card, StatusIndicator } from "@ds/index";
import type { IncidentSummary } from "@ds/types";

import { fetchIncidents } from "../api/client";

export function OfficersPage() {
  const [rows, setRows] = useState<IncidentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchIncidents({ limit: 100, sort_by: "newest" })
      .then((payload) => {
        setRows(payload.items);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const officers = useMemo(() => {
    const map = new Map<string, { name: string; load: number; status: string }>();
    for (const incident of rows) {
      const name = incident.assigned_officer;
      if (!name) continue;
      const current = map.get(name) ?? { name, load: 0, status: incident.status };
      current.load += 1;
      map.set(name, current);
    }
    return [...map.values()];
  }, [rows]);

  return (
    <AppShell title="Officers" operationalStatus="VERIFIED">
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : officers.length === 0 ? (
        <p className="ds-empty">No officers assigned.</p>
      ) : (
        <div className="ds-grid ds-grid--cards">
          {officers.map((officer) => (
            <Card key={officer.name} variant="officer-card">
              <h3 className="ds-display-semibold" style={{ margin: "0 0 8px", fontSize: "var(--font-size-md)" }}>
                {officer.name}
              </h3>
              <div className="ds-meta-row">
                <span className="ds-mono">load {officer.load}</span>
                <StatusIndicator status={officer.status} />
              </div>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}
