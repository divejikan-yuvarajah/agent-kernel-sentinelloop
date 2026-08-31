import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Dashboard" },
  { to: "/incidents", label: "Active Incidents" },
  { to: "/evidence", label: "Evidence Review" },
  { to: "/officers", label: "Officers" },
  { to: "/analytics", label: "Analytics" },
  { to: "/settings", label: "Settings" },
];

export function Sidebar() {
  return (
    <aside className="ds-sidebar" aria-label="Primary">
      <div className="ds-sidebar__brand">
        SentinelLoop
        <span>COMMAND CENTER</span>
      </div>
      <nav className="ds-nav">
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.to === "/"} className="ds-nav__link">
            {link.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
