import { useState } from "react";

import { Modal, Panel } from "@ds/index";
import type { EvidenceItem } from "@ds/types";

import { EvidenceImage } from "../EvidenceImage";

type Props = {
  items: EvidenceItem[];
  beforeSrc?: string | null;
  afterSrc?: string | null;
};

function VerificationLabel({ stage }: { stage?: string | null }) {
  if (stage === "verification") {
    return <span className="ii-evidence__state ii-evidence__state--verified">Verified</span>;
  }
  if (stage === "rejected") {
    return <span className="ii-evidence__state ii-evidence__state--rejected">Rejected</span>;
  }
  return <span className="ii-evidence__state ii-evidence__state--pending">Pending Verification</span>;
}

function formatClock(value?: string | null) {
  if (!value) return "—";
  if (/^\d{1,2}:\d{2}/.test(value)) return value.slice(0, 5);
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function EvidenceGallery({ items, beforeSrc, afterSrc }: Props) {
  const [active, setActive] = useState<EvidenceItem | null>(null);
  const before = items.filter((item) => item.stage === "report" || item.stage === "before");
  const after = items.filter((item) => item.stage === "verification" || item.stage === "after");
  const other = items.filter((item) => !before.includes(item) && !after.includes(item));

  const sections: { title: string; rows: EvidenceItem[]; fallback?: string | null }[] = [
    { title: "Initial Hazard Evidence", rows: before, fallback: beforeSrc },
    { title: "Resolution Evidence", rows: after, fallback: afterSrc },
  ];
  if (other.length) sections.push({ title: "Additional Evidence", rows: other });

  return (
    <Panel title="Evidence & Verification" className="ii-evidence">
      {items.length === 0 && !beforeSrc && !afterSrc ? (
        <p className="ds-empty">No evidence uploaded yet</p>
      ) : (
        sections.map((section) => {
          const rows =
            section.rows.length > 0
              ? section.rows
              : section.fallback
                ? [
                    {
                      id: section.title,
                      label: section.title,
                      source: "evidence",
                      timestamp: "",
                      kind: "image" as const,
                      stage: section.title.includes("Resolution") ? "verification" : "report",
                      imageSrc: section.fallback,
                      uploaded_by: section.title.includes("Resolution") ? "Officer" : "Worker",
                    },
                  ]
                : [];
          if (!rows.length) return null;
          return (
            <section key={section.title} className="ii-evidence__section">
              <h3>{section.title}</h3>
              <ul className="ii-evidence__grid">
                {rows.map((item) => (
                  <li key={item.id}>
                    <button type="button" className="ii-evidence__card" onClick={() => setActive(item)}>
                      <EvidenceImage src={item.imageSrc} alt={item.label} ratio="4/3" />
                      <div className="ii-evidence__meta">
                        <p>
                          Uploaded by: <strong>{item.uploaded_by || "Officer"}</strong>
                        </p>
                        <p className="ds-mono">Time: {formatClock(item.timestamp)}</p>
                        <VerificationLabel stage={item.stage} />
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          );
        })
      )}

      <Modal open={Boolean(active)} title={active?.label || "Evidence"} onClose={() => setActive(null)}>
        {active ? (
          <div className="ii-evidence__viewer">
            <EvidenceImage src={active.imageSrc} alt={active.label} ratio="16/9" />
            <p>
              Uploaded by: {active.uploaded_by || "Officer"} · {formatClock(active.timestamp)}
            </p>
            <VerificationLabel stage={active.stage} />
          </div>
        ) : null}
      </Modal>
    </Panel>
  );
}
