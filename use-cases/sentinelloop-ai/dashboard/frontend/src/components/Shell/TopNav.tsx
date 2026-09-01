import { Link, NavLink } from "react-router-dom";

import { Icon } from "@ds/components/Icon";

import { NotificationCenter } from "./NotificationCenter";
import { RouterStatusPill } from "./RouterStatusPill";
import { SystemIndicators } from "./SystemIndicators";
import { UserMenu } from "./UserMenu";
import { SHELL_PRIMARY_NAV } from "./shellNav";

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
        <nav className="sl-topnav__links" aria-label="Primary">
          {SHELL_PRIMARY_NAV.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) => `sl-topnav__link${isActive ? " is-active" : ""}`}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="sl-topnav__trail">
        <p className="sl-topnav__page" title={title}>
          {title}
        </p>
        <SystemIndicators className="sl-topnav__sys" />
        <RouterStatusPill />
        {demo ? <span className="ds-demo-pill">DEMO</span> : null}
        <NotificationCenter count={notificationCount} />
        <UserMenu name={operatorName} role={operatorRole} />
      </div>
    </header>
  );
}
