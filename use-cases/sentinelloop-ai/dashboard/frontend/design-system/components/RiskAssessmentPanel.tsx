import type { RiskAssessment } from "../types";
import { Panel } from "./Panel";
import { RiskIndicator } from "./RiskIndicator";

type Props = {
  assessment: RiskAssessment;
};

export function RiskAssessmentPanel({ assessment }: Props) {
  return (
    <Panel title="AI risk assessment">
      <div className="ds-meta-row" style={{ marginTop: 0 }}>
        <RiskIndicator level={assessment.level} score={assessment.score} />
        <span className="ds-mono">confidence {assessment.confidence}%</span>
      </div>
      <p style={{ margin: "16px 0 8px", fontSize: "var(--font-size-xs)", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--chalk-muted)" }}>
        Detected hazards
      </p>
      <ul style={{ margin: 0, paddingLeft: 16 }}>
        {assessment.hazards.map((hazard) => (
          <li key={hazard}>{hazard}</li>
        ))}
      </ul>
      <p style={{ margin: "16px 0 0", color: "var(--chalk-muted)", fontSize: "var(--font-size-sm)" }}>
        {assessment.reasoning}
      </p>
    </Panel>
  );
}
