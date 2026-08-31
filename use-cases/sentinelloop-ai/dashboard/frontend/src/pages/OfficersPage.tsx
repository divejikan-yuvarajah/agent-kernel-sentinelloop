import { useEffect, useMemo, useState } from "react";

import { AppShell, Card, StatusIndicator } from "@ds/index";
import type { IncidentSummary } from "@ds/types";

import { fetchIncidents } from "../api/client";
import { users } from "../data/demoData";
import { useDemoMode } from "../demo/useDemoMode";

export function OfficersPage() {
  const [demo] = useDemoMode();
  const [rows, setRows] = useState<IncidentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchIncidents({ limit: 100, sort_by: "newest" })
      .then((payload) => {
        setRows(payload.items);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [demo]);

  const officers = useMemo(() => {
    if (demo) {
      const load = new Map<string, number>();
      for (const incident of rows) {
        const name = incident.assigned_officer;
        if (!name) continue;
        load.set(name, (load.get(name) || 0) + 1);
      }
      return users
        .filter((user) => user.role !== "Worker")
        .map((user) => ({
          name: user.name,
          team: user.team,
          role: user.role,
          status: user.status,
          load: load.get(user.name) || 0,
        }));
    }
    const map = new Map<string, { name: string; team: string; role: string; load: number; status: string }>();
    for (const incident of rows) {
      const name = incident.assigned_officer;
      if (!name) continue;
      const current = map.get(name) ?? {
        name,
        team: incident.assigned_team || "Field",
        role: "Officer",
        load: 0,
        status: incident.status,
      };
      current.load += 1;
      map.set(name, current);
    }
    return [...map.values()];
  }, [rows, demo]);

  return (
    <AppShell title="Officers" operationalStatus="VERIFIED">
      <p className="ds-page-lead">Duty load for Horizon Engineering Workshop response teams.</p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : loading ? (
        <p className="ds-empty">Loading officers…</p>
      ) : officers.length === 0 ? (
        <p className="ds-empty">No officers assigned. All safety issues are currently resolved.</p>
      ) : (
        <div className="ds-grid ds-grid--cards">
          {officers.map((officer) => (
            <Card key={officer.name} variant="officer-card">
              <h3 className="ds-display-semibold" style={{ margin: "0 0 8px", fontSize: "var(--font-size-md)" }}>
                {officer.name}
              </h3>
              <p className="ds-mono" style={{ margin: "0 0 8px", color: "var(--chalk-muted)" }}>
                {officer.role} · {officer.team}
              </p>
              <div className="ds-meta-row">
                <span className="ds-mono">load {officer.load}</span>
                <StatusIndicator status={officer.status === "Active" ? "VERIFIED" : officer.status} />
              </div>
            </Card>
          ))}
        </div>
      )}
    </AppShell>
  );
}
