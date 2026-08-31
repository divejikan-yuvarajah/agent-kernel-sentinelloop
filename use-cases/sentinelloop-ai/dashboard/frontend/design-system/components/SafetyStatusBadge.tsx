type Props = {
  status?: string | null;
};

function tone(status: string) {
  const key = status.toLowerCase();
  if (key.includes("block")) return "blocked";
  if (key.includes("review")) return "review";
  return "validated";
}

export function SafetyStatusBadge({ status }: Props) {
  if (!status) return null;
  const kind = tone(status);
  return (
    <span className={`ds-badge ds-safety ds-safety--${kind}`} title="Safety Status">
      <span className="ds-safety__mark" aria-hidden="true" />
      Safety Status {status}
    </span>
  );
}
