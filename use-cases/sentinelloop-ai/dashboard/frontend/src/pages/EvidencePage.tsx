import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { AppShell, EvidenceViewer, IncidentOverviewCard, Panel } from "@ds/index";
import type { EvidenceItem, IncidentSummary } from "@ds/types";

import { fetchIncidents } from "../api/client";
import { evidenceRecords } from "../data/demoData";
import { evidenceRecord, incidentPair } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

export function EvidencePage() {
  const navigate = useNavigate();
  const [demo] = useDemoMode();
  const [rows, setRows] = useState<IncidentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchIncidents({ limit: 40, sort_by: "newest" })
      .then((payload) => {
        setRows(payload.items);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [demo]);

  const gallery: EvidenceItem[] = demo
    ? evidenceRecords.map((item) => {
        const known = evidenceRecord(item.id);
        const pair = incidentPair(item.incident_id);
        return {
          id: item.id,
          label: item.label,
          source: item.source,
          timestamp: item.date,
          kind: item.kind,
          stage: item.stage,
          imageSrc: known?.src || (item.stage === "verification" ? pair.after : pair.before),
          channel: "channel" in item ? String(item.channel || "") : item.source,
          uploaded_by: "uploaded_by" in item ? String(item.uploaded_by || "") : undefined,
        };
      })
    : [];

  return (
    <AppShell title="Evidence review" operationalStatus="INVESTIGATING">
      <p className="ds-page-lead">
        Worker photos and officer uploads live on each incident record. The dashboard does not mutate evidence.
      </p>
      {gallery.length > 0 ? (
        <Panel title="Before / after gallery" style={{ marginBottom: 24 }}>
          <EvidenceViewer
            items={gallery}
            renderImage={(item) => <EvidenceImage src={item.imageSrc} alt={item.label} />}
          />
        </Panel>
      ) : null}
      <Panel title="Inbox">
        {error ? (
          <p className="ds-empty" role="alert">
            {error}
          </p>
        ) : loading ? (
          <p className="ds-empty">Loading evidence inbox…</p>
        ) : rows.length === 0 ? (
          <p className="ds-empty">No evidence attached. All safety issues are currently resolved.</p>
        ) : (
          <div className="ds-grid ds-grid--cards">
            {rows.map((incident) => (
              <IncidentOverviewCard
                key={incident.incident_id}
                incident={incident}
                imageSrc={incidentPair(incident.incident_id, incident.category).before}
                onOpen={(id) => navigate(`/incidents/${id}`)}
              />
            ))}
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
