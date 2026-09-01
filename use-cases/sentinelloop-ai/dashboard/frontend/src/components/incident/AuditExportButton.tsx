import { Button } from "@ds/index";

type Props = {
  onClick: () => void;
  loading?: boolean;
};

export function AuditExportButton({ onClick, loading = false }: Props) {
  return (
    <Button data-testid="audit-export" onClick={onClick} disabled={loading}>
      {loading ? "Exporting…" : "Export audit trail"}
    </Button>
  );
}
