import { Panel } from "@ds/index";

type Props = {
  guidance: string | null | undefined;
  knowledgeBase: string | null | undefined;
};

function linesFromGuidance(guidance: string) {
  return guidance
    .split(/\n|(?<=\.)\s+/)
    .map((line) => line.replace(/^\d+\.\s*/, "").trim())
    .filter(Boolean)
    .slice(0, 6);
}

export function GuidancePanel({ guidance, knowledgeBase }: Props) {
  const lines = guidance ? linesFromGuidance(guidance) : [];
  return (
    <Panel title="Immediate Safety Guidance" className="ii-guidance">
      {lines.length === 0 ? (
        <p className="ds-empty">No knowledge-base guidance recorded</p>
      ) : (
        <ol className="ii-guidance__list">
          {lines.map((line, index) => (
            <li key={`${index}-${line.slice(0, 24)}`}>{line}</li>
          ))}
        </ol>
      )}
      <p className="ii-guidance__source ds-mono">
        Source:{" "}
        {knowledgeBase
          ? `${knowledgeBase.replace(/_/g, " ").replace(/\.(md|pdf)$/i, "")} Knowledge Base`
          : "Safety Knowledge Base"}
      </p>
    </Panel>
  );
}
