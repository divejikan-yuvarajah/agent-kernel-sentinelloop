import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { AppShell, Button, Card, Panel } from "@ds/index";
import type { GuardrailComplianceExport, GuardrailStatus } from "@ds/types";

import { fetchComplianceExport, fetchGuardrailStatus } from "../api/client";
import { useDemoMode } from "../demo/useDemoMode";

function downloadReport(report: GuardrailComplianceExport) {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = `SentinelLoop_Safety_Compliance_${report.generated_at.slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(href);
}

export function SafetyCenterPage() {
  const [demo] = useDemoMode();
  const [status, setStatus] = useState<GuardrailStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    fetchGuardrailStatus()
      .then((payload) => {
        setStatus(payload);
        setError(null);
      })
      .catch((err: Error) => setError(err.message));
  }, [demo]);

  function exportReport() {
    setExporting(true);
    fetchComplianceExport()
      .then(downloadReport)
      .catch((err: Error) => setError(err.message))
      .finally(() => setExporting(false));
  }

  const metrics = status?.metrics;
  const charts = status?.charts;
  const chartMax = Math.max(
    charts?.guidance_validation_success_rate ?? 0,
    charts?.anonymous_reports_percentage ?? 0,
    charts?.incidents_requiring_human_review ?? 0,
    charts?.blocked_ai_outputs ?? 0,
    1,
  );

  return (
    <AppShell title="AI Safety Center" operationalStatus="RESOLVED">
      <p className="ds-page-lead">
        Guardrails Active. AI suggests, guardrails validate, then a safe output is released with an audit trail.
      </p>
      {error ? (
        <p className="ds-empty" role="alert">
          {error}
        </p>
      ) : null}
      <div className="ds-grid ds-grid--split" style={{ marginBottom: 24 }}>
        <Panel title="Guidance Validation">
          <p className="ds-metric__value">Passed</p>
          <p className="ds-mono">98%</p>
        </Panel>
        <Panel title="AI Safety Block">
          <p>Unsafe instruction prevented</p>
        </Panel>
      </div>
      <div className="ds-grid ds-grid--metrics">
        {(status?.cards ?? []).map((card) => (
          <Card key={card.name} variant="analytics-card">
            <p className="ds-metric__label">{card.active ? "✓" : "–"} {card.name}</p>
            <p className="ds-metric__value">{card.active ? "Active" : "Off"}</p>
            <p className="ds-mono" style={{ marginTop: 8 }}>
              SPEC.md: {card.spec_rule}
            </p>
          </Card>
        ))}
      </div>
      <Panel title="Guardrail Metrics" style={{ marginTop: 24 }}>
        <div className="ds-grid ds-grid--metrics">
          <Card variant="analytics-card">
            <p className="ds-metric__label">Total validations</p>
            <p className="ds-metric__value">{metrics?.total_validations ?? 0}</p>
          </Card>
          <Card variant="analytics-card">
            <p className="ds-metric__label">Passed</p>
            <p className="ds-metric__value">{metrics?.passed ?? 0}</p>
          </Card>
          <Card variant="analytics-card">
            <p className="ds-metric__label">Blocked</p>
            <p className="ds-metric__value">{metrics?.blocked ?? 0}</p>
          </Card>
          <Card variant="analytics-card">
            <p className="ds-metric__label">Warnings</p>
            <p className="ds-metric__value">{metrics?.warnings ?? 0}</p>
          </Card>
        </div>
      </Panel>
      <Panel title="Safety Violations" style={{ marginTop: 24 }}>
        <p>Guidance hallucinations: {status?.violations.guidance_hallucinations ?? 0}</p>
        <p>Privacy attempts: {status?.violations.privacy_attempts ?? 0}</p>
        <p>Blocked closures: {status?.violations.blocked_closures ?? 0}</p>
        <p>Budget blocks: {status?.violations.budget_blocks ?? 0}</p>
      </Panel>
      {demo ? (
        <div className="ds-grid ds-grid--split" style={{ marginTop: 24 }}>
          <Panel title="Guidance validation · passed">
            <p>Status: Approved</p>
            <p>Knowledge source: electrical_safety.md</p>
            <p>Confidence: 98%</p>
            <p className="ds-mono">INC-2026-00421 · Keep away from exposed wires, sparks, smoke, or damaged electrical equipment.</p>
          </Panel>
          <Panel title="Unsafe AI suggestion · blocked">
            <p>Reason: Instruction not found in knowledge base</p>
            <p>Action: Blocked</p>
            <p className="ds-mono">INC-2026-00415 · Invented electrical isolation step was not released.</p>
          </Panel>
        </div>
      ) : null}
      <Panel title="Safety Compliance Overview" style={{ marginTop: 24 }}>
        <div className="ds-chart" role="img" aria-label="Safety compliance overview">
          {[
            { label: "Guidance %", value: charts?.guidance_validation_success_rate ?? 0 },
            { label: "Human review", value: charts?.incidents_requiring_human_review ?? 0 },
            { label: "Blocked", value: charts?.blocked_ai_outputs ?? 0 },
            { label: "Anonymous %", value: charts?.anonymous_reports_percentage ?? 0 },
            { label: "Cost/inc", value: charts?.average_ai_cost_per_incident ?? 0 },
          ].map((point) => (
            <div key={point.label} className="ds-chart__col">
              <div className="ds-chart__bar" style={{ height: `${Math.round((Number(point.value) / chartMax) * 100)}%` }} />
              <span className="ds-chart__label">{point.label}</span>
            </div>
          ))}
        </div>
        <p className="ds-mono" style={{ marginTop: 12 }}>
          Average AI cost per incident: {charts?.average_ai_cost_per_incident ?? 0}
        </p>
      </Panel>
      <div className="ds-toolbar" style={{ marginTop: 24 }}>
        <Button onClick={exportReport} disabled={exporting}>
          Export Safety Compliance Report
        </Button>
        <Link to="/safety/review">Review Required</Link>
        <Link to="/safety/debug">Guardrail Debug Console</Link>
      </div>
    </AppShell>
  );
}
