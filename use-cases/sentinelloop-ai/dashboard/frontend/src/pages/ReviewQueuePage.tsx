import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { AppShell, Button, Panel } from "@ds/index";
import type { ReviewQueueItem } from "@ds/types";

import { fetchReviewQueue } from "../api/client";

export function ReviewQueuePage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReviewQueue()
      .then((payload) => {
        setItems(payload.items);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <AppShell title="Review Required" operationalStatus="OPEN">
      <p className="ds-page-lead">
        High and Critical incidents wait for an authorized Slack Closed action. Dashboard buttons stay disabled
        because this surface is read-only.
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : items.length === 0 ? (
        <p className="ds-empty">No incidents waiting for human review.</p>
      ) : (
        items.map((item) => (
          <Panel key={item.incident_id} title={item.incident_id} style={{ marginBottom: 16 }}>
            <p>Risk: {item.risk_level}</p>
            <p>Reason: {item.reason}</p>
            <p>Assigned reviewer: {item.assigned_reviewer ?? "Unassigned"}</p>
            <p>Waiting time: {item.waiting_time ?? "—"}</p>
            <p className="ds-mono">{item.action_hint}</p>
            <div className="ds-toolbar">
              {item.actions.map((action) => (
                <Button key={action} disabled title="Human approval required according to SPEC.md">
                  {action}
                </Button>
              ))}
              <Button variant="ghost" onClick={() => navigate(`/incidents/${encodeURIComponent(item.incident_id)}`)}>
                Open incident
              </Button>
            </div>
          </Panel>
        ))
      )}
      <p>
        <Link to="/safety">Back to AI Safety Center</Link>
      </p>
    </AppShell>
  );
}
