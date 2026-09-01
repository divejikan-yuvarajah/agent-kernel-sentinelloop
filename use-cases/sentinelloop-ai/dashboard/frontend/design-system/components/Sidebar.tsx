import { NavLink } from "react-router-dom";

import { NAV_GROUPS } from "@/navigation";

import { Icon } from "./Icon";

const EMERGENCY_LABEL = "Emergency Command Center";

type Props = {
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  onNavigate?: () => void;
};

function navEndsAtExactPath(to: string) {
  return to !== "/emergency" && to !== "/incidents";
}

export function Sidebar({ collapsed = false, onToggleCollapsed, onNavigate }: Props) {
  return (
    <aside className="ds-sidebar" aria-label="Primary">
      <div className="ds-sidebar__brand">
        <img
          className="ds-sidebar__mark"
          src="/images/sentinelloop-logo.png"
          alt=""
          width={44}
          height={44}
        />
        <div className="ds-sidebar__copy">
          SentinelLoop
          <span>COMMAND CENTER</span>
        </div>
      </div>
      <nav className="ds-nav">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="ds-nav__group">
            <p className="ds-nav__group-label">{group.label}</p>
            {group.links.map((link) => {
              const emergency = link.label === EMERGENCY_LABEL;
              return (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={navEndsAtExactPath(link.to)}
                  className={emergency ? "ds-nav__link ds-nav__link--emergency" : "ds-nav__link"}
                  title={link.label}
                  onClick={onNavigate}
                >
                  <Icon name={link.icon} />
                  <span className="ds-nav__text">{link.label}</span>
                </NavLink>
              );
            })}
          </div>
        ))}
      </nav>
      {onToggleCollapsed ? (
        <button
          type="button"
          className="ds-sidebar__collapse"
          onClick={onToggleCollapsed}
          aria-pressed={collapsed}
          title={collapsed ? "Expand side menu" : "Collapse side menu"}
        >
          <Icon name={collapsed ? "expand" : "collapse"} />
          <span>{collapsed ? "Expand" : "Collapse"}</span>
        </button>
      ) : null}
    </aside>
  );
}
