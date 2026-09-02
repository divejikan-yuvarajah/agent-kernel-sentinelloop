import { Link } from "react-router-dom";

import {
  AGENT_KERNEL_URL,
  DASHBOARD_PATH,
  GITHUB_REPO_URL,
  NAV_LINKS,
  SANDBOX_PATH,
  SDGS,
  TEAM_ZATROZ,
} from "../constants";

export function Footer() {
  return (
    <footer className="sl-footer">
      <div className="sl-wrap sl-footer__grid">
        <div>
          <p className="sl-brand sl-brand--footer">
            <img src="/images/sentinelloop-logo.png" alt="" width={32} height={32} />
            SentinelLoop AI
          </p>
          <p className="sl-footer__tag">
            A worker report becomes a tracked case — in Sinhala, Tamil, or English.
          </p>
          <ul className="sl-sdg" aria-label="UN Sustainable Development Goals">
            {SDGS.map((goal) => (
              <li key={goal.code} title={goal.title}>
                <span>SDG {goal.code}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="sl-footer__col">
          <p className="sl-footer__heading">On this page</p>
          <ul>
            {NAV_LINKS.map((item) => (
              <li key={item.href}>
                <a href={item.href}>{item.label}</a>
              </li>
            ))}
            <li>
              <Link to={SANDBOX_PATH}>Try it live</Link>
            </li>
            <li>
              <Link to={DASHBOARD_PATH}>Live dashboard</Link>
            </li>
          </ul>
        </div>
        <div className="sl-footer__col sl-footer__meta">
          <p className="sl-footer__heading">{TEAM_ZATROZ.name}</p>
          <p className="sl-footer__team">{TEAM_ZATROZ.members.join(", ")}</p>
          <p>Built for IDEALIZE 2026 — Agent Kernel Mini-Competition</p>
          <p>
            <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
              GitHub repository
            </a>
          </p>
        </div>
      </div>
      <p className="sl-footer__powered">
        Built by <strong>Team Zatroz</strong>
        {" · "}
        Powered by{" "}
        <a href={AGENT_KERNEL_URL} target="_blank" rel="noopener noreferrer">
          Agent Kernel
        </a>
      </p>
    </footer>
  );
}
