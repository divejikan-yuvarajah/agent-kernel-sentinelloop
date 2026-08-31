import { StatusIndicator } from "./StatusIndicator";

type Props = {
  title: string;
  operationalStatus: string;
  notificationCount?: number;
  operatorName: string;
  operatorRole: string;
  brand?: string;
  openIncidentCount?: number;
};

export function Header({
  title,
  operationalStatus,
  notificationCount = 0,
  operatorName,
  operatorRole,
  brand,
  openIncidentCount,
}: Props) {
  const hasAlerts = notificationCount > 0;
  const padded = openIncidentCount === undefined ? null : String(openIncidentCount).padStart(2, "0");
  return (
    <header className="ds-header">
      <div>
        {brand ? (
          <p className="ds-brand ds-display" style={{ margin: 0 }}>
            {brand}
          </p>
        ) : (
          <p className="ds-page-title" style={{ margin: 0, fontSize: "var(--font-size-lg)" }}>
            {title}
          </p>
        )}
      </div>
      <div className="ds-header__status">
        <StatusIndicator status={operationalStatus} />
        {padded !== null ? (
          <span className="ds-mono ds-header__open" aria-label={`${openIncidentCount} open incidents`}>
            OPEN INCIDENTS {padded}
          </span>
        ) : (
          <span className="ds-mono" style={{ fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
            OPS LIVE
          </span>
        )}
      </div>
      <div className="ds-header__meta">
        <button
          type="button"
          className="ds-notify"
          aria-label={hasAlerts ? `${notificationCount} unread operational alerts` : "No unread alerts"}
        >
          {hasAlerts ? <span className="ds-notify__count" aria-hidden="true" /> : null}
          <span aria-hidden="true">!</span>
        </button>
        <div className="ds-profile">
          <span className="ds-profile__mark" aria-hidden="true">
            {operatorName
              .split(" ")
              .map((part) => part[0])
              .join("")
              .slice(0, 2)}
          </span>
          <div>
            <div>{operatorName}</div>
            <div className="ds-mono" style={{ fontSize: "var(--font-size-xs)", color: "var(--chalk-muted)" }}>
              {operatorRole}
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
