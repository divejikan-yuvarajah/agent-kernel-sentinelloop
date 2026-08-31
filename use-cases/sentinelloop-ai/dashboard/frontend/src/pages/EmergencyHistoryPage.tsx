import { AppShell, Panel } from "@ds/index";

import { fetchEmergencies, type EmergencyCommandCenter } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";
import { useEffect, useState } from "react";

import { EmergencyHistoryTable } from "./EmergencyPage";

export function EmergencyHistoryPage() {
  const [demo] = useDemoMode();
  const [data, setData] = useState<EmergencyCommandCenter | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEmergencies()
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [demo]);

  return (
    <AppShell title="Emergency Response History" operationalStatus="INVESTIGATING">
      <p className="ds-page-lead">Every emergency bypass, channel, detection time, and resolution on one audit table.</p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : null}
      <Panel title="Emergency Response History">
        {!data?.history.length ? (
          <p className="ds-empty">No emergency history.</p>
        ) : (
          <EmergencyHistoryTable rows={data.history} />
        )}
      </Panel>
    </AppShell>
  );
}
