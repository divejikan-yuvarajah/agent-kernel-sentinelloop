import { Link } from "react-router-dom";

import { AppShell, Badge, Panel } from "@ds/index";

import { slackThread } from "../data/demoData";
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
    </AppShell>
  );
}
