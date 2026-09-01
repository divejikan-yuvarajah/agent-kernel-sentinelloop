import {
  AppShell,
  Badge,
  Button,
  Card,
  InputField,
  Panel,
  RiskIndicator,
  SelectDropdown,
  StatusIndicator,
  TableRow,
} from "@ds/index";

export function DesignSystemPage() {
  return (
    <AppShell title="Design system" operationalStatus="VERIFIED">
      <p className="ds-page-lead">Token and primitive catalog. Maroon is brand. Saturated risk color appears only on status.</p>
      <div className="ds-grid ds-grid--split">
        <Panel title="Surfaces">
          <div className="ds-grid ds-grid--cards">
            <Card variant="analytics-card">Panel on ink. Chalk text.</Card>
            <Card variant="incident-card" riskLevel="CRITICAL">
              Incident card with 5px Critical tab.
            </Card>
            <Card variant="activity-card" loading />
            <Card variant="evidence-card" empty emptyMessage="Empty state" />
          </div>
        </Panel>
        <Panel title="Controls">
          <div className="ds-toolbar">
            <Button>Primary action</Button>
            <Button variant="ghost">Ghost</Button>
            <Badge>Neutral badge</Badge>
          </div>
          <div className="ds-meta-row">
            <StatusIndicator status="OPEN" />
            <StatusIndicator status="INVESTIGATING" />
            <StatusIndicator status="VERIFIED" />
            <StatusIndicator status="RESOLVED" />
          </div>
          <div className="ds-meta-row">
            <RiskIndicator level="LOW" score={4} />
            <RiskIndicator level="MEDIUM" score={9} />
            <RiskIndicator level="HIGH" score={12} />
            <RiskIndicator level="CRITICAL" score={20} />
          </div>
          <InputField label="Sample field" name="sample" placeholder="Mono used only for IDs" />
          <SelectDropdown
            label="Sample select"
            name="sample-select"
            options={[{ value: "a", label: "Option A" }]}
          />
          <table className="ds-table" style={{ marginTop: 16 }}>
            <thead>
              <tr>
                <th>ID</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              <TableRow cells={[<span className="ds-mono">INC-0042</span>, <span className="ds-mono">20</span>]} />
            </tbody>
          </table>
        </Panel>
      </div>
    </AppShell>
  );
}
