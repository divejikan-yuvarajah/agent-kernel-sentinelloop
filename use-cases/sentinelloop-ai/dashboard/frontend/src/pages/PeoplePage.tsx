import { useMemo, useState } from "react";

import { AppShell, Card, InputField, StatusIndicator } from "@ds/index";

import { incidents, users, workers } from "../data/demoData";
import { avatarFor } from "../data/demoImages";
import { useDemoMode } from "../demo/useDemoMode";

export function PeoplePage() {
  const [demo] = useDemoMode();
  const [query, setQuery] = useState("");
  const needle = query.toLowerCase();

  const officerHits = useMemo(
    () =>
      users.filter((user) =>
        `${user.name} ${user.role} ${user.team}`.toLowerCase().includes(needle),
      ),
    [needle],
  );
  const workerHits = useMemo(
    () =>
      workers.filter((worker) =>
        `${worker.name} ${worker.role} ${worker.language}`.toLowerCase().includes(needle),
      ),
    [needle],
  );
  const incidentHits = useMemo(
    () =>
      incidents.filter((row) =>
        `${row.incident_id} ${row.category} ${row.location} ${row.equipment} ${row.title}`
          .toLowerCase()
          .includes(needle),
      ),
    [needle],
  );

  return (
    <AppShell title="User Management" operationalStatus="VERIFIED">
      <p className="ds-page-lead">
        Safety officers, maintenance crews, and workshop reporters for Horizon Engineering Workshop.
      </p>
      {demo ? (
        <>
          <div className="ds-toolbar">
            <InputField
              label="Search people, equipment, or reports"
              name="people-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Electrical, CNC, Kasun, Nimal"
            />
          </div>
          <h2 className="ds-page-title" style={{ fontSize: "var(--font-size-md)" }}>
            Safety officers & maintenance
          </h2>
          <div className="ds-grid ds-grid--cards">
            {officerHits.map((user) => (
              <Card key={user.id} variant="officer-card">
                <img className="ds-avatar" src={avatarFor(user.name)} alt="" />
                <h3 className="ds-display-semibold" style={{ margin: "12px 0 8px", fontSize: "var(--font-size-md)" }}>
                  {user.name}
                </h3>
                <p>{user.role}</p>
                <p className="ds-mono">{user.team}</p>
                <StatusIndicator status="VERIFIED" />
              </Card>
            ))}
          </div>
          <h2 className="ds-page-title" style={{ fontSize: "var(--font-size-md)", marginTop: 32 }}>
            Workers
          </h2>
          <div className="ds-grid ds-grid--cards">
            {workerHits.map((worker) => (
              <Card key={worker.id} variant="officer-card">
                <img className="ds-avatar" src={avatarFor(worker.name, worker.anonymous)} alt="" />
                <h3 className="ds-display-semibold" style={{ margin: "12px 0 8px", fontSize: "var(--font-size-md)" }}>
                  {worker.anonymous ? "Anonymous reporter" : worker.name}
                </h3>
                <p>{worker.role}</p>
                <p className="ds-mono">Language: {worker.language}</p>
              </Card>
            ))}
          </div>
          {query ? (
            <section style={{ marginTop: 32 }}>
              <h2 className="ds-page-title" style={{ fontSize: "var(--font-size-md)" }}>
                Matching reports
              </h2>
              {incidentHits.length === 0 ? (
                <p className="ds-empty">No matching incidents, equipment, or workers.</p>
              ) : (
                incidentHits.slice(0, 8).map((row) => (
                  <p key={row.incident_id}>
                    <span className="ds-mono">{row.incident_id}</span> · {row.category} · {row.location}
                    {row.equipment ? ` · ${row.equipment}` : ""}
                  </p>
                ))
              )}
            </section>
          ) : null}
        </>
      ) : (
        <p className="ds-empty">User directories are not stored in the five-table backend. Enable Demo Mode to preview the workshop roster.</p>
      )}
    </AppShell>
  );
}
