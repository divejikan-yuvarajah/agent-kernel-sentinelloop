import { Button, Panel } from "@ds/index";

import { liveStatusLabel, primaryActionForStatus } from "./statusMap";

type Props = {
  assignedTeam: string | null | undefined;
  assignedOfficer: string | null | undefined;
  status: string;
  autoCloseDisabled?: boolean;
  onAction?: (action: string) => void;
  note?: string | null;
};

export function AssignmentPanel({
  assignedTeam,
  assignedOfficer,
  status,
  autoCloseDisabled = false,
  onAction,
  note,
}: Props) {
  const live = liveStatusLabel(status);
  const accepted = ["Accepted", "In Progress", "Awaiting Verification", "Resolved", "Closed"].includes(live);
  const primary = primaryActionForStatus(status);

  return (
    <Panel title="Response Team" className="ii-assign">
      <dl className="ii-overview__grid">
        <div>
          <dt>Assigned</dt>
          <dd>{assignedTeam || "Unassigned"}</dd>
        </div>
        <div>
          <dt>Accepted</dt>
          <dd>{accepted ? "Yes" : "No"}</dd>
        </div>
        <div>
          <dt>Officer</dt>
          <dd>{assignedOfficer || "—"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{live}</dd>
        </div>
      </dl>
      <div className="ds-toolbar ii-assign__actions">
        <Button onClick={() => onAction?.("accept")}>Accept</Button>
        <Button variant="ghost" onClick={() => onAction?.("reassign")}>
          Reassign
        </Button>
        <Button variant="ghost" onClick={() => onAction?.("escalate")}>
          Escalate
        </Button>
      </div>
      <div className="ds-toolbar ii-assign__primary">
        <Button
          disabled={primary.label === "Close Incident" && autoCloseDisabled}
          title={autoCloseDisabled ? "Human approval required before close" : primary.hint}
          onClick={() => onAction?.(primary.label)}
        >
          {primary.label}
        </Button>
      </div>
      <p className="ii-assign__hint">{primary.hint}</p>
      {note ? <p className="ds-mono">{note}</p> : null}
    </Panel>
  );
}
