import { Link } from "react-router-dom";

import { AppShell, Badge, Panel } from "@ds/index";

import { slackThread } from "../data/demoData";
import { incidentThumbnail } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

export function CoordinationPage() {
  const [demo] = useDemoMode();
  return (
    <AppShell title="Slack Coordination" operationalStatus="INVESTIGATING">
      <p className="ds-page-lead">
        Simulated Slack thread for Horizon Engineering Workshop. The live bot still posts to real channels when Demo Mode is off.
      </p>
      {demo ? (
        <Panel title={`Channel ${slackThread.channel}`}>
          <EvidenceImage src={incidentThumbnail(slackThread.incident)} alt="Assigned electrical hazard" ratio="16/9" />
          <p>
            Incident:{" "}
            <Link to={`/incidents/${slackThread.incident}`}>{slackThread.incident}</Link>
          </p>
          <p>Assigned team: {slackThread.team}</p>
          <div className="ds-meta-row">
            {slackThread.actions.map((action) => (
              <Badge key={action}>✓ {action}</Badge>
            ))}
          </div>
          <ul className="ds-slack">
            {slackThread.messages.map((message) => (
              <li key={`${message.author}-${message.text}`}>
                <strong>{message.author}</strong>
                <span>{message.text}</span>
              </li>
            ))}
          </ul>
        </Panel>
      ) : (
        <p className="ds-empty">No coordination threads in this session. All safety issues are currently resolved.</p>
      )}
      <Panel className="ds-predict-panel" title="Preventive Inspection Request" style={{ marginTop: 24 }}>
        <p>🔍 Preventive Inspection Request</p>
        <p>Location: Chemical Storage Room</p>
        <p>Reason: 3 chemical leak reports detected in 25 days.</p>
        <p>Recommended Action: Schedule safety inspection.</p>
        <p>Priority: Attention Needed</p>
        <p className="ds-mono">Requested by: AI Prevention Agent · message type inspection_request</p>
      </Panel>
    </AppShell>
  );
}
