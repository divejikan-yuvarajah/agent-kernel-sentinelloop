import type { RouterStatus } from "../types";

type Props = {
  status: RouterStatus | null;
  loading?: boolean;
};

function money(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `$${value.toFixed(value >= 1 ? 2 : 3)}`;
}

export function RouterStatusStrip({ status, loading = false }: Props) {
  if (loading) {
    return (
      <section className="ds-router" aria-busy="true" aria-label="Model router status">
        <span className="ds-skeleton ds-skeleton--line" />
        <span className="ds-skeleton ds-skeleton--line" />
      </section>
    );
  }
  if (!status || (!status.ledger_available && status.recent_calls.length === 0)) {
    return (
      <section className="ds-router" aria-label="Model router status">
        <p className="ds-empty" style={{ padding: 0, textAlign: "left" }}>
          No model calls available.
        </p>
      </section>
    );
  }
  const remainingPct =
    status.budget.budget_limit && status.budget.budget_limit > 0
      ? Math.max(0, 100 - (status.budget.usage_percentage ?? 0))
      : null;
  const calls = status.recent_calls.slice(0, 2);
  return (
    <section className="ds-router" aria-label="AI model router transparency">
      <p className="ds-router__kicker" title="We control AI costs.">
        Model router
      </p>
      <div className="ds-router__calls">
        {calls.length === 0 ? (
          <p className="ds-empty" style={{ padding: 0, textAlign: "left" }}>
            No model calls available.
          </p>
        ) : (
          calls.map((call, index) => (
            <div key={`${call.timestamp}-${index}`} className="ds-router__call">
              <span className="ds-mono">{call.model_role ?? "MODEL"}</span>
              <span>Role: {call.agent_role ?? "—"}</span>
              <span className="ds-mono">Cost: {money(call.cost_usd)}</span>
            </div>
          ))
        )}
      </div>
      <div className="ds-router__budget">
        <span>
          Current spend:{" "}
          <span className="ds-mono">
            {money(status.budget.spent)}
            {status.budget.budget_limit != null ? ` / ${money(status.budget.budget_limit)}` : ""}
          </span>
        </span>
        <span>
          Remaining: <span className="ds-mono">{remainingPct == null ? "—" : `${remainingPct.toFixed(1)}%`}</span>
        </span>
      </div>
    </section>
  );
}
