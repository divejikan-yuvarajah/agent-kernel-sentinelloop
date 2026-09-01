import { Panel } from "@ds/index";

type Check = { label: string; done: boolean };

type Props = {
  checks: Check[];
};

export function AuditCompletenessCard({ checks }: Props) {
  return (
    <Panel title="Audit Completeness" className="ii-completeness">
      <ul className="ii-completeness__list">
        {checks.map((check) => (
          <li key={check.label} className={check.done ? "is-done" : "is-missing"}>
            <span aria-hidden="true">{check.done ? "✓" : "○"}</span>
            {check.label}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
