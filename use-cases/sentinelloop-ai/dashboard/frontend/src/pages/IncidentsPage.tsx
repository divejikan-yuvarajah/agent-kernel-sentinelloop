import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { AppShell, IncidentOverviewCard, InputField, SelectDropdown } from "@ds/index";
import type { IncidentSummary } from "@ds/types";

import { fetchIncidents } from "../api/client";

export function IncidentsPage() {
  const navigate = useNavigate();
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
  }, [risk]);

  const visible = rows.filter((item) => {
    const haystack = `${item.incident_id} ${item.title ?? ""} ${item.location ?? ""}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  });

  return (
    <AppShell title="Active incidents" operationalStatus="INVESTIGATING" notificationCount={visible.length}>
      <div className="ds-toolbar">
        <InputField
          label="Search"
          name="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="ID, location, or title"
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
        <p className="ds-empty">No active incidents.</p>
      ) : (
        <div className="ds-grid ds-grid--cards">
          {visible.map((incident) => (
            <IncidentOverviewCard
              key={incident.incident_id}
              incident={incident}
              onOpen={(id) => navigate(`/incidents/${id}`)}
            />
          ))}
        </div>
      )}
    </AppShell>
  );
}
