import { Link } from "react-router-dom";

import { Icon } from "@ds/components/Icon";

import { NotificationCenter } from "./NotificationCenter";
import { RouterStatusPill } from "./RouterStatusPill";
import { UserMenu } from "./UserMenu";

type Props = {
  title: string;
  operatorName: string;
  operatorRole: string;
  notificationCount?: number;
  demo?: boolean;
  navOpen?: boolean;
  onMenuClick?: () => void;
};

export function TopNav({
  title,
  operatorName,
  operatorRole,
  notificationCount,
  demo = false,
  navOpen = false,
  onMenuClick,
}: Props) {
  return (
    <header className="sl-topnav" aria-label="SentinelLoop command navigation">
      <div className="sl-topnav__lead">
        {onMenuClick ? (
          <button
            type="button"
            className="sl-topnav__menu"
            aria-label={navOpen ? "Close navigation" : "Open menu"}
            aria-expanded={navOpen}
            onClick={onMenuClick}
          >
            <Icon name={navOpen ? "close" : "menu"} />
            <span className="sl-topnav__menu-label">Menu</span>
          </button>
        ) : null}
        <Link to="/dashboard" className="sl-topnav__brand" aria-label="SentinelLoop dashboard home">
          <img src="/images/sentinelloop-logo.png" alt="" width={28} height={28} />
          <span>SENTINELLOOP</span>
        </Link>
        <p className="sl-topnav__page" title={title}>
          {title}
        </p>
      </div>
      <div className="sl-topnav__trail">
        <Link to="/sandbox" className="sl-topnav__live" aria-label="Try It Live sandbox">
          Try It Live
        </Link>
        <Link to="/report" className="sl-topnav__log" aria-label="Log a hazard">
          <span aria-hidden="true">+</span>
          <span className="sl-topnav__log-label-full">Log hazard</span>
        </Link>
        <RouterStatusPill />
        {demo ? <span className="ds-demo-pill">DEMO</span> : null}
        <NotificationCenter count={notificationCount} />
        <UserMenu name={operatorName} role={operatorRole} />
      </div>
    </header>
  );
}
