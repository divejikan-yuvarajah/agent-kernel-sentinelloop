import { Link } from "react-router-dom";

import { AppShell, Badge, Panel, StatusIndicator } from "@ds/index";

import { duplicateGroup } from "../data/demoData";
import { demoImages } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

export function DuplicatesPage() {
  const [demo] = useDemoMode();
  return (
    <AppShell title="Duplicate Detection" operationalStatus="OPEN">
      <p className="ds-page-lead">
        Recurring hazards at the same location are grouped so supervisors can escalate before a fourth report.
      </p>
      {demo ? (
        <>
          <Panel title="Recurring hazard detected">
            <div className="ds-meta-row" style={{ marginTop: 0 }}>
              <Badge>Escalation {duplicateGroup.escalation}</Badge>
              <StatusIndicator status="OPEN" />
            </div>
            <p>Category: {duplicateGroup.category}</p>
            <p>Location: {duplicateGroup.location}</p>
            <p>Reports: {duplicateGroup.reports}</p>
            <p>Period: {duplicateGroup.period}</p>
            <p>
              <Link to="/incidents/DEMO-HORIZON-004">Open DEMO-HORIZON-004</Link>
              {" · "}
              <Link to="/incidents/INC-2026-00421">Open INC-2026-00421</Link>
            </p>
          </Panel>
          <Panel title="Linked reports" style={{ marginTop: 24 }}>
            <p>Same location: {duplicateGroup.location}</p>
            <div className="ds-photo-grid" style={{ margin: "16px 0" }}>
              {[demoImages.incidents["INC-2026-00421"].before, demoImages.hazards.electrical[1], demoImages.hazards.electrical[2]].map(
                (src, index) => (
                  <article key={src}>
                    <EvidenceImage src={src} alt={`Recurring report ${index + 1}`} />
                    <p className="ds-mono">{index + 1}.</p>
                  </article>
                ),
              )}
            </div>
            {duplicateGroup.items.map((item) => (
              <p key={item.id}>
                <span className="ds-mono">{item.date}</span> · {item.text} · {item.worker}
              </p>
            ))}
          </Panel>
        </>
      ) : (
        <p className="ds-empty">No recurring hazards in the current window. All safety issues are currently resolved.</p>
      )}
    </AppShell>
  );
}
