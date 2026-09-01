import { useMemo, useState } from "react";

import { AppShell, Button, Panel } from "@ds/index";

import { knowledgeBase } from "../data/demoData";

export function KnowledgePage() {
  const [selected, setSelected] = useState(knowledgeBase[0]?.pdf ?? "");
  const active = useMemo(() => knowledgeBase.find((doc) => doc.pdf === selected) ?? knowledgeBase[0], [selected]);

  return (
    <AppShell title="Knowledge Base" operationalStatus="VERIFIED">
      <p className="ds-page-lead">
        Approved safety guides in PDF, each with site regulations, worker duties, and prohibited actions. Read them
        here or download a copy. Worker guidance stays grounded in these documents — invented repair steps are blocked.
      </p>

      <div className="ds-grid ds-grid--cards kb-guide-grid">
        {knowledgeBase.map((doc) => {
          const isActive = doc.pdf === active?.pdf;
          return (
            <Panel key={doc.pdf} title={doc.category} className={isActive ? "kb-guide-card kb-guide-card--active" : "kb-guide-card"}>
              <p className="ds-metric__label">Safety Guide · {doc.ruleCount} rules in PDF</p>
              <ul>
                {doc.rules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
              <div className="kb-guide-card__actions">
                <Button
                  variant={isActive ? "primary" : "ghost"}
                  onClick={() => setSelected(doc.pdf)}
                  aria-pressed={isActive}
                >
                  Read PDF
                </Button>
                <a className="ds-btn" href={doc.pdf} download>
                  Download
                </a>
              </div>
            </Panel>
          );
        })}
      </div>

      {active ? (
        <Panel title={`${active.category} — PDF guide`} className="kb-reader">
          <div className="kb-reader__toolbar">
            <p className="ds-metric__label" style={{ margin: 0 }}>
              {active.file}
            </p>
            <div className="kb-reader__links">
              <a className="ds-btn" href={active.pdf} target="_blank" rel="noreferrer">
                Open in new tab
              </a>
              <a className="ds-btn" href={active.pdf} download>
                Download PDF
              </a>
            </div>
          </div>
          <iframe
            className="kb-reader__frame"
            title={`${active.category} safety guide PDF`}
            src={`${active.pdf}#view=FitH`}
          />
        </Panel>
      ) : null}
    </AppShell>
  );
}
