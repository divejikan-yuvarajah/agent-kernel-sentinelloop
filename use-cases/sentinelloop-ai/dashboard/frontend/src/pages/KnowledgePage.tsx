import { AppShell, Panel } from "@ds/index";

import { knowledgeBase } from "../data/demoData";
import { useDemoMode } from "../demo/useDemoMode";

export function KnowledgePage() {
  const [demo] = useDemoMode();
  return (
    <AppShell title="Knowledge Base" operationalStatus="VERIFIED">
      <p className="ds-page-lead">
        Guidance is grounded in these files. Invented repair steps are blocked by the guardrail.
      </p>
      {demo ? (
        <div className="ds-grid ds-grid--cards">
          {knowledgeBase.map((doc) => (
            <Panel key={doc.file} title={doc.category}>
              <p className="ds-mono">{doc.file}</p>
              <ul>
                {doc.rules.map((rule) => (
                  <li key={rule}>{rule}</li>
                ))}
              </ul>
            </Panel>
          ))}
        </div>
      ) : (
        <p className="ds-empty">Knowledge files are loaded by the API. Enable Demo Mode to preview Horizon rules.</p>
      )}
    </AppShell>
  );
}
