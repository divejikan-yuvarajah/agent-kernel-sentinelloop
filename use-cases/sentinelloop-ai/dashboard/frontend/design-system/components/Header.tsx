import { Link } from "react-router-dom";

import { Icon } from "./Icon";
import { StatusIndicator } from "./StatusIndicator";

type Props = {
  title: string;
  operationalStatus: string;
  notificationCount?: number;
  operatorName: string;
  operatorRole: string;
  brand?: string;
  subtitle?: string;
  openIncidentCount?: number;
  demo?: boolean;
  notifyHref?: string;
  navOpen?: boolean;
  onMenuClick?: () => void;
};

export function Header({
  title,
  operationalStatus,
  notificationCount = 0,
  operatorName,
  operatorRole,
  brand,
  subtitle,
  openIncidentCount,
  demo = false,
  notifyHref = "/notifications",
  navOpen = false,
  onMenuClick,
}: Props) {
  const hasAlerts = notificationCount > 0;
  const padded = openIncidentCount === undefined ? null : String(openIncidentCount).padStart(2, "0");
  return (
    <header className="ds-header">
      <div className="ds-header__lead">
        {onMenuClick ? (
          <button
            type="button"
            className="ds-header__menu"
            aria-label={navOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={navOpen}
            onClick={onMenuClick}
          >
            <Icon name={navOpen ? "close" : "menu"} />
          </button>
        ) : null}
        <img className="ds-header__mark" src="/images/sentinelloop-logo.png" alt="" width={28} height={28} />
        {brand ? (
          <div className="ds-header__brand-block">
            <p className="ds-brand ds-display ds-header__title">{brand}</p>
            {subtitle ? <p className="ds-header__subtitle">{subtitle}</p> : null}
          </div>
        ) : (
          <div className="ds-header__brand-block">
            <p className="ds-header__title">{title}</p>
            {subtitle ? <p className="ds-header__subtitle">{subtitle}</p> : null}
          </div>
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
        {demo ? (
          <span className="ds-demo-pill" title="Horizon Engineering Workshop sample data">
            DEMO
          </span>
        ) : null}
      </div>
      <div className="ds-header__meta">
        <Link
          to={notifyHref}
          className="ds-notify"
          aria-label={hasAlerts ? `${notificationCount} unread operational alerts` : "No unread alerts"}
        >
          {hasAlerts ? <span className="ds-notify__count" aria-hidden="true" /> : null}
          <span aria-hidden="true">!</span>
        </Link>
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
