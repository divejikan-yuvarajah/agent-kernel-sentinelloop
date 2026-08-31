import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  AppShell,
  IncidentOverviewCard,
  InputField,
  RiskIndicator,
  SelectDropdown,
  StatusIndicator,
  TableRow,
} from "@ds/index";
import { normalizeRisk } from "@ds/colors";
import type { IncidentSummary } from "@ds/types";

import { fetchIncidents } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";

function formatDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toISOString().slice(0, 10);
}

export function IncidentsPage() {
  const navigate = useNavigate();
  const [demo] = useDemoMode();
  const [query, setQuery] = useState("");
  const [risk, setRisk] = useState("ALL");
  const [rows, setRows] = useState<IncidentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchIncidents({
      limit: 50,
      sort_by: "newest",
      risk_level: risk === "ALL" ? undefined : risk,
    })
      .then((payload) => {
        if (cancelled) return;
        setRows(payload.items);
        setError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [risk, demo]);

  const visible = rows.filter((item) => {
    const haystack = [
      item.incident_id,
      item.title,
      item.location,
      item.category,
      item.assigned_officer,
      item.assigned_team,
      item.reporter_name,
      item.qr_equipment,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query.toLowerCase());
  });

  return (
    <AppShell title="Incident Management" operationalStatus="INVESTIGATING" notificationCount={visible.length}>
      <p className="ds-page-lead">
        Search electrical, CNC, workers, or locations. Open a row to follow the full AI decision path.
      </p>
      <div className="ds-toolbar">
        <InputField
          label="Search"
          name="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Electrical, CNC, worker, location"
        />
        <SelectDropdown
          label="Risk"
          name="risk"
          value={risk}
          onChange={(event) => setRisk(event.target.value)}
          options={[
            { value: "ALL", label: "All levels" },
            { value: "CRITICAL", label: "Critical" },
            { value: "HIGH", label: "High" },
            { value: "MEDIUM", label: "Medium" },
            { value: "LOW", label: "Low" },
          ]}
        />
      </div>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : loading ? (
        <div className="ds-grid ds-grid--cards">
          <IncidentOverviewCard
            loading
            incident={{
              incident_id: "—",
              title: null,
              category: null,
              location: null,
              status: "OPEN",
              risk_level: null,
              risk_score: null,
              created_at: null,
              updated_at: null,
              elapsed_time: null,
              assigned_officer: null,
              duplicate_count: 0,
              loop_stage: null,
            }}
          />
        </div>
      ) : visible.length === 0 ? (
        <p className="ds-empty">No active incidents. All safety issues are currently resolved.</p>
      ) : (
        <>
          <div style={{ overflowX: "auto" }}>
            <table className="ds-table">
              <thead>
                <tr>
                  <th>Incident ID</th>
                  <th>Category</th>
                  <th>Location</th>
                  <th>Reported by</th>
                  <th>Risk</th>
                  <th>Status</th>
                  <th>Assigned team</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((incident) => (
                  <TableRow
                    key={incident.incident_id}
                    cells={[
                      <button
                        key="id"
                        type="button"
                        className="ds-mono"
                        style={{ background: "none", border: 0, color: "inherit", cursor: "pointer", padding: 0 }}
                        onClick={() => navigate(`/incidents/${incident.incident_id}`)}
                      >
                        {incident.incident_id}
                      </button>,
                      incident.category ?? "—",
                      incident.location ?? "—",
                      incident.reporter_name || (incident.is_anonymous ? "Anonymous" : "Worker"),
                      <RiskIndicator
                        key="risk"
                        level={normalizeRisk(incident.risk_level ?? "MEDIUM")}
                        score={incident.risk_score ?? 0}
                      />,
                      <StatusIndicator key="status" status={incident.status} />,
                      incident.assigned_team || incident.assigned_officer || "Unassigned",
                      formatDate(incident.created_at),
                    ]}
                  />
                ))}
              </tbody>
            </table>
          </div>
          <div className="ds-grid ds-grid--cards" style={{ marginTop: 24 }}>
            {visible.slice(0, 6).map((incident) => (
              <IncidentOverviewCard
                key={`${incident.incident_id}-card`}
                incident={incident}
                onOpen={(id) => navigate(`/incidents/${id}`)}
              />
            ))}
          </div>
        </>
      )}
    </AppShell>
  );
}
