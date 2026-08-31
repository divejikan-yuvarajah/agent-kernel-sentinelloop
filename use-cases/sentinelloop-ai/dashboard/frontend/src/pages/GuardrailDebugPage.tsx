import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AppShell, Panel } from "@ds/index";
import type { GuardrailDebugEvent } from "@ds/types";

import { fetchGuardrailDebug } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";

export function GuardrailDebugPage() {
  const [demo] = useDemoMode();
  const [events, setEvents] = useState<GuardrailDebugEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchGuardrailDebug()
      .then((payload) => {
        setEvents(payload);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [demo]);

  return (
    <AppShell title="Guardrail Debug Console" operationalStatus="RESOLVED">
      <p className="ds-page-lead">
        Admin-only operator view. Never shown to workers. Lists input, validation result, rule, and decision.
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : events.length === 0 ? (
        <p className="ds-empty">No guardrail events in this process yet.</p>
      ) : (
        events
          .slice()
          .reverse()
          .map((item, index) => (
            <Panel key={`${item.timestamp}-${index}`} title={`${item.guardrail} · ${item.event}`}>
              <p>Timestamp: {item.timestamp}</p>
              <p>Input: {item.input_summary || "—"}</p>
              <p>Validation result: {item.validation_result}</p>
              <p>Agent output / decision: {item.agent_output || item.decision || "—"}</p>
              <p>Rule violated: {item.rule_violated || "none"}</p>
              <p>Incident: {item.incident_id || "—"}</p>
            </Panel>
          ))
      )}
      <p>
        <Link to="/safety">Back to AI Safety Center</Link>
      </p>
    </AppShell>
  );
}
