import { AppShell, Button, Card, Panel } from "@ds/index";

import { auditLogs, kpis, monthlyReports, organization } from "../data/demoData";
import { demoImages } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

function downloadReport() {
  const body = [
    `Monthly Safety Report`,
    `${organization.name}`,
    `August 2026`,
    `Generated: 31 Aug 2026`,
    `Total incidents: ${kpis.totalIncidents}`,
    `Critical: ${kpis.criticalIncidents}`,
    `Resolved this month: ${kpis.resolvedThisMonth}`,
    `Average response: ${kpis.averageResponseTime}`,
    `AI detection accuracy: ${kpis.aiDetectionAccuracy}`,
  ].join("\n");
  const blob = new Blob([body], { type: "text/plain" });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = "Horizon_Monthly_Safety_Report_August_2026.txt";
  link.click();
  URL.revokeObjectURL(href);
}

export function ReportsPage() {
  const [demo] = useDemoMode();
  const max = Math.max(...monthlyReports.map((item) => item.count), 1);
  return (
    <AppShell title="Reports" operationalStatus="RESOLVED">
      <p className="ds-page-lead">Downloadable safety packs for the workshop. Live exports still use the audit API.</p>
      {demo ? (
        <>
          <Panel title="Monthly Safety Report · August 2026">
            <EvidenceImage src={demoImages.reports.august} alt="Monthly safety report preview" ratio="16/9" />
            <p>Generated: 31 Aug 2026</p>
            <p>Total incidents: {kpis.totalIncidents}</p>
            <p>Critical: {kpis.criticalIncidents}</p>
            <p>Resolved: {kpis.resolvedThisMonth}</p>
            <div className="ds-toolbar" style={{ marginTop: 16, marginBottom: 0 }}>
              <Button onClick={downloadReport}>Download August report</Button>
            </div>
          </Panel>
          <Panel title="Monthly volume" style={{ marginTop: 24 }}>
            <div className="ds-chart" role="img" aria-label="Monthly report counts">
              {monthlyReports.map((item) => (
                <div key={item.month} className="ds-chart__col">
                  <div className="ds-chart__bar" style={{ height: `${Math.round((item.count / max) * 100)}%` }} />
                  <span className="ds-chart__label">
                    {item.month.slice(0, 3)}
                    <br />
                    {item.count}
                  </span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Closure audit log" style={{ marginTop: 24 }}>
            {auditLogs.map((entry) => (
              <p key={`${entry.time}-${entry.action}`} className="ds-mono">
                {entry.time.slice(0, 16).replace("T", " ")} · {entry.actor} · {entry.action} · {entry.target}
              </p>
            ))}
          </Panel>
        </>
      ) : (
        <Card variant="analytics-card" empty emptyMessage="No generated reports in this session." />
      )}
    </AppShell>
  );
}
