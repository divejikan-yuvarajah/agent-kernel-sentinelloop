import { Panel } from "@ds/index";
import { normalizeRisk } from "@ds/colors";

import { RiskBadge } from "./RiskBadge";

type Props = {
  severity: number | null | undefined;
  likelihood: number | null | undefined;
  riskLevel: string | null;
  riskScore: number | null;
  explanation: string | null;
};

function Meter({ label, value, max = 5 }: { label: string; value: number; max?: number }) {
  const filled = Math.max(0, Math.min(max, value));
  return (
    <div className="ii-meter">
      <div className="ii-meter__head">
        <span>{label}</span>
        <span className="ds-mono">
          {filled}/{max}
        </span>
      </div>
      <div className="ii-meter__track" aria-hidden="true">
        {Array.from({ length: max }, (_, index) => (
          <span key={index} className={index < filled ? "ii-meter__cell is-filled" : "ii-meter__cell"} />
        ))}
      </div>
    </div>
  );
}

export function RiskExplanation({ severity, likelihood, riskLevel, riskScore, explanation }: Props) {
  const level = normalizeRisk(riskLevel || "MEDIUM");
  const sev = severity ?? 0;
  const like = likelihood ?? 0;

  return (
    <Panel title="How SentinelLoop Made This Decision" className="ii-risk-explain">
      <div className="ii-risk-explain__split">
        <article className="ii-risk-explain__ai">
          <p className="ii-kicker">AI Estimation</p>
          <p className="ii-risk-explain__label">AI Suggested Inputs</p>
          <p>
            AI Estimated Severity: <strong className="ds-mono">{sev || "—"} / 5</strong>
          </p>
          <p>
            AI Estimated Likelihood: <strong className="ds-mono">{like || "—"} / 5</strong>
          </p>
          <p className="ii-risk-explain__note">The model estimates inputs. It does not set the final risk level.</p>
        </article>
        <article className="ii-risk-explain__rule">
          <p className="ii-kicker">Rule-Based Decision</p>
          <p className="ii-risk-explain__label">Deterministic Risk Engine</p>
          <p>
            Final Risk: <RiskBadge level={level} />
          </p>
          <p>
            Score: <strong className="ds-mono">{riskScore ?? "—"}</strong>
          </p>
          <p className="ii-risk-explain__note">Calculated by safety matrix</p>
        </article>
      </div>

      <div className="ii-risk-explain__viz" aria-label="Risk calculation visualization">
        <Meter label="Severity" value={sev} />
        <Meter label="Likelihood" value={like} />
        <p className="ii-risk-explain__score">
          Risk Score <strong className="ds-mono">{riskScore ?? "—"}</strong> {level}
        </p>
      </div>

      <aside className="ii-risk-callout" aria-labelledby="why-risk-title">
        <p className="ii-risk-callout__label" id="why-risk-title">
          Why this risk level exists
        </p>
        <p className="ii-risk-callout__text">{explanation || "No calculate_risk() explanation on record."}</p>
      </aside>
    </Panel>
  );
}
