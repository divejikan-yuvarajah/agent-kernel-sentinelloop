import { normalizeStatus, type IncidentStatusKey } from "../colors";

const LABELS: Record<IncidentStatusKey, string> = {
  OPEN: "Open",
  INVESTIGATING: "Investigating",
  VERIFIED: "Verified",
  RESOLVED: "Resolved",
};

type Props = {
  status: string;
  className?: string;
};

export function StatusIndicator({ status, className = "" }: Props) {
  const key = normalizeStatus(status);
  return (
    <span className={`ds-status ds-status--${key} ${className}`.trim()} role="status">
      <span className="ds-status__dot" aria-hidden="true" />
      {LABELS[key]}
    </span>
  );
}
