import { AppShell, Panel } from "@ds/index";

import { knowledgeBase } from "../data/demoData";
import { categoryImage } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

const KB_CATEGORY: Record<string, string> = {
  "Electrical Safety": "electrical",
  "Fire Safety": "fire/smoke",
  "Chemical Safety": "chemical",
  "Machine Safety": "machine",
  "PPE Safety": "ppe",
  "General Hazards": "structural",
};

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
              <EvidenceImage src={categoryImage(KB_CATEGORY[doc.category])} alt={doc.category} ratio="16/9" />
              <p className="ds-mono">{doc.file}</p>
              <p>Rules:</p>
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
