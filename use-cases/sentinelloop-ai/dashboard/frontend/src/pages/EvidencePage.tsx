import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { AppShell, IncidentOverviewCard, Panel } from "@ds/index";
import type { IncidentSummary } from "@ds/types";

import { fetchIncidents } from "../api/client";

export function EvidencePage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<IncidentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchIncidents({ limit: 40, sort_by: "newest" })
      .then((payload) => {
        setRows(payload.items);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <AppShell title="Evidence review" operationalStatus="INVESTIGATING">
      <p className="ds-page-lead">
        Worker photos and officer uploads live on each incident record. The dashboard does not mutate evidence.
      </p>
      <Panel title="Inbox">
        {error ? (
          <p className="ds-empty" role="alert">
            {error}
          </p>
        ) : rows.length === 0 ? (
          <p className="ds-empty">No evidence attached.</p>
        ) : (
          <div className="ds-grid ds-grid--cards">
            {rows.map((incident) => (
              <IncidentOverviewCard
                key={incident.incident_id}
                incident={incident}
                onOpen={(id) => navigate(`/incidents/${id}`)}
              />
            ))}
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
