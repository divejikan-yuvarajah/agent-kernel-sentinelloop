import { useEffect, useState } from "react";

import { AppShell, Card, Panel } from "@ds/index";

import { fetchAiUsage, type AiUsageBreakdown } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";

function money(value: number | null | undefined) {
  if (value == null) return "—";
  return `$${value.toFixed(2)}`;
}

export function AiUsagePage() {
  const [demo] = useDemoMode();
  const [usage, setUsage] = useState<AiUsageBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchAiUsage()
      .then((payload) => {
        setUsage(payload);
        setError(null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [demo]);

  return (
    <AppShell title="AI Usage Dashboard" operationalStatus="RESOLVED">
      <p className="ds-page-lead">
        Text, vision, and voice spend share one OpenRouter budget ceiling. API keys are never shown.
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : loading ? (
        <p className="ds-empty">Loading AI usage…</p>
      ) : (
        <>
          <div className="ds-grid ds-grid--metrics">
            <Card variant="analytics-card">
              <p className="ds-metric__label">Text Cost</p>
              <p className="ds-metric__value">{money(usage?.text_cost_usd)}</p>
            </Card>
            <Card variant="analytics-card">
              <p className="ds-metric__label">Vision Cost</p>
              <p className="ds-metric__value">{money(usage?.vision_cost_usd)}</p>
            </Card>
            <Card variant="analytics-card">
              <p className="ds-metric__label">Voice Cost</p>
              <p className="ds-metric__value">{money(usage?.voice_cost_usd)}</p>
            </Card>
            <Card variant="analytics-card">
              <p className="ds-metric__label">Remaining Budget</p>
              <p className="ds-metric__value">{money(usage?.remaining_budget_usd)}</p>
            </Card>
          </div>
          <Panel title="Budget" style={{ marginTop: 24 }}>
            <p>Total spend: {money(usage?.total_cost_usd)}</p>
            <p>Ceiling: {money(usage?.budget_ceiling_usd)}</p>
          </Panel>
        </>
      )}
    </AppShell>
  );
}
