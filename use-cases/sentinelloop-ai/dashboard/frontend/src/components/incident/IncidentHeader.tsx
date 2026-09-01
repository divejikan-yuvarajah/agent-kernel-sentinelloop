import { ChannelBadge, SafetyStatusBadge, StatusIndicator } from "@ds/index";

import { AuditExportButton } from "./AuditExportButton";
import { RiskBadge } from "./RiskBadge";
import { liveStatusLabel, liveStatusTone } from "./statusMap";

type Props = {
  incidentId: string;
  title: string | null;
  category: string | null;
  location: string | null;
  status: string;
  riskLevel: string;
  riskScore: number | null;
  elapsed: string | null;
  createdAt: string | null;
  safetyStatus?: string | null;
  inputChannel?: string | null;
  onExport: () => void;
  exportLoading?: boolean;
};

function reportedLabel(elapsed: string | null, createdAt: string | null) {
  if (elapsed) return `Reported ${elapsed} ago`;
  if (!createdAt) return "Reported recently";
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return "Reported recently";
  return `Reported ${date.toLocaleString()}`;
}

export function IncidentHeader({
  incidentId,
  title,
  category,
  location,
  status,
  riskLevel,
  riskScore,
  elapsed,
  createdAt,
  safetyStatus,
  inputChannel,
  onExport,
  exportLoading,
}: Props) {
  const live = liveStatusLabel(status);
  const tone = liveStatusTone(status);

  return (
    <header className="ii-header">
      <div className="ii-header__top">
        <div className="ii-header__identity">
          <p className="ii-header__id ds-mono">{incidentId}</p>
          <div className="ii-header__badges">
            <RiskBadge level={riskLevel} score={riskScore} />
            <span className={`ii-live ii-live--${tone}`} role="status">
              <span className="ii-live__dot" aria-hidden="true" />
              {live}
            </span>
            <StatusIndicator status={status} />
            {safetyStatus ? <SafetyStatusBadge status={safetyStatus} /> : null}
            <ChannelBadge channel={inputChannel} />
          </div>
        </div>
        <AuditExportButton onClick={onExport} loading={exportLoading} />
      </div>
      <h1 className="ii-header__title">{title || category || incidentId}</h1>
      <p className="ii-header__location">
        <span className="ii-kicker">Location</span>
        {location || "Unknown location"}
      </p>
      <p className="ii-header__reported ds-mono">{reportedLabel(elapsed, createdAt)}</p>
    </header>
  );
}
