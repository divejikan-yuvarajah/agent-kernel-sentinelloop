import { NavLink } from "react-router-dom";

const GROUPS = [
  {
    label: "Operations",
    links: [
      { to: "/", label: "Dashboard" },
      { to: "/incidents", label: "Incident Management" },
      { to: "/follow-up", label: "Follow-up" },
      { to: "/evidence", label: "Evidence Review" },
    ],
  },
  {
    label: "Coordination",
    links: [
      { to: "/coordination", label: "Slack Coordination" },
      { to: "/duplicates", label: "Duplicate Detection" },
    ],
  },
  {
    label: "People",
    links: [
      { to: "/officers", label: "Officers" },
      { to: "/people", label: "User Management" },
    ],
  },
  {
    label: "Intelligence",
    links: [
      { to: "/analytics", label: "Analytics" },
      { to: "/telegram", label: "Telegram Bot" },
      { to: "/reports", label: "Reports" },
      { to: "/knowledge", label: "Knowledge Base" },
      { to: "/notifications", label: "Alerts" },
    ],
  },
  {
    label: "Safety",
    links: [
      { to: "/safety", label: "AI Safety Center" },
      { to: "/safety/review", label: "Review Required" },
      { to: "/settings", label: "Settings" },
    ],
  },
];

export function Sidebar() {
  return (
    <aside className="ds-sidebar" aria-label="Primary">
      <div className="ds-sidebar__brand">
        SentinelLoop
        <span>COMMAND CENTER</span>
      </div>
      <nav className="ds-nav">
        {GROUPS.map((group) => (
          <div key={group.label} className="ds-nav__group">
            <p className="ds-nav__group-label">{group.label}</p>
            {group.links.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.to === "/"} className="ds-nav__link">
                {link.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  );
}
