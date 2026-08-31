import type { ReactNode } from "react";

import type { EvidenceItem } from "../types";
import { Card } from "./Card";

type Props = {
  items: EvidenceItem[];
  renderImage?: (item: EvidenceItem) => ReactNode;
};

export function EvidenceViewer({ items, renderImage }: Props) {
  if (items.length === 0) {
    return <Card variant="evidence-card" empty emptyMessage="No evidence attached." />;
  }
  return (
    <div className="ds-evidence">
      {items.map((item) => (
        <Card key={item.id} variant="evidence-card" className="ds-evidence__item">
          {renderImage ? (
            <div className="ds-evidence__frame">{renderImage(item)}</div>
          ) : item.imageSrc ? (
            <div className="ds-evidence__frame">
              <img src={item.imageSrc} alt={item.label} loading="lazy" />
            </div>
          ) : (
            <div className="ds-evidence__frame" data-stage={item.stage ?? undefined} aria-hidden="true" />
          )}
          <div className="ds-evidence__meta">
            <p className="ds-evidence__id">{item.id}</p>
            {item.stage ? (
              <p className="ds-mono" style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", letterSpacing: "0.06em" }}>
                {item.stage === "report" ? "Before" : item.stage === "verification" ? "After" : item.stage}
              </p>
            ) : null}
            <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-sm)" }}>{item.label}</p>
            <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
              {item.timestamp}
            </p>
            <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
              Source: {item.channel || item.source}
            </p>
            {item.kind === "voice" ? (
              <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>Type: Voice Evidence</p>
            ) : item.kind === "image" ? (
              <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>Type: Image Evidence</p>
            ) : null}
            {item.uploaded_by ? (
              <p style={{ margin: "4px 0 0", fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>Uploader: {item.uploaded_by}</p>
            ) : null}
          </div>
        </Card>
      ))}
    </div>
  );
}
