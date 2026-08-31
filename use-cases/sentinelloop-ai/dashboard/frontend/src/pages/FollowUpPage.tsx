import { Link } from "react-router-dom";

import { AppShell, Panel, StatusIndicator } from "@ds/index";

import { followUpCases } from "../data/demoData";
import { incidentPair } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

export function FollowUpPage() {
  const [demo] = useDemoMode();
  const pending = followUpCases.filter((item) => !item.closed_by);
  const done = followUpCases.filter((item) => item.closed_by);
  return (
    <AppShell title="Follow-up Verification" operationalStatus="INVESTIGATING">
      <p className="ds-page-lead">
        Workers confirm the area is safe before an officer closes the record. High and Critical still need Slack Closed.
      </p>
      {demo ? (
        <div className="ds-grid ds-grid--split">
          <Panel title="Waiting confirmation">
            {pending.map((item) => (
              <article key={item.incident_id} style={{ marginBottom: 16 }}>
                <EvidenceImage src={incidentPair(item.incident_id).before} alt={item.title} />
                <p className="ds-mono">
                  <Link to={`/incidents/${item.incident_id}`}>{item.incident_id}</Link>
                </p>
                <p>{item.title}</p>
                <p>Worker response: {item.worker_response}</p>
                <StatusIndicator status="AWAITING_VERIFICATION" />
              </article>
            ))}
          </Panel>
          <Panel title="Completed verification">
            {done.map((item) => (
              <article key={item.incident_id} style={{ marginBottom: 16 }}>
                <div className="ds-before-after">
                  <EvidenceImage src={incidentPair(item.incident_id).before} alt="Before" />
                  <EvidenceImage src={incidentPair(item.incident_id).after} alt="After" />
                </div>
                <p className="ds-mono">
                  <Link to={`/incidents/${item.incident_id}`}>{item.incident_id}</Link>
                </p>
                <p>Worker response: {item.worker_response}</p>
                <p>
                  Closed by: {item.closed_by} · {item.date}
                </p>
                <StatusIndicator status="CLOSED" />
              </article>
            ))}
          </Panel>
        </div>
      ) : (
        <p className="ds-empty">No verifications waiting. All safety issues are currently resolved.</p>
      )}
    </AppShell>
  );
}
