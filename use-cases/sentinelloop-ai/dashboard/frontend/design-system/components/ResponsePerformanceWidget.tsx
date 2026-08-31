type Props = {
  avgResponse: string | null;
  avgResolution: string | null;
  fastest?: string | null;
  slowest?: string | null;
};

export function ResponsePerformanceWidget({ avgResponse, avgResolution, fastest, slowest }: Props) {
  return (
    <section aria-label="Response performance">
      <p className="ds-metric__label" title="We coordinate response.">
        Response performance
      </p>
      <dl className="ds-perf">
        <div>
          <dt>Average response</dt>
          <dd className="ds-mono">{avgResponse ?? "—"}</dd>
        </div>
        <div>
          <dt>Resolution time</dt>
          <dd className="ds-mono">{avgResolution ?? "—"}</dd>
        </div>
        <div>
          <dt>Fastest response</dt>
          <dd className="ds-mono">{fastest ?? "—"}</dd>
        </div>
        <div>
          <dt>Slowest response</dt>
          <dd className="ds-mono">{slowest ?? "—"}</dd>
        </div>
      </dl>
    </section>
  );
}
