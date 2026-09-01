import { AGENT_KERNEL_URL, GITHUB_REPO_URL, SDGS } from "../constants";

export function Footer() {
  return (
    <footer className="sl-footer">
      <div className="sl-wrap sl-footer__grid">
        <div>
          <p className="sl-brand sl-brand--footer">
            <img src="/images/sentinelloop-logo.png" alt="" width={32} height={32} />
            SentinelLoop AI
          </p>
          <ul className="sl-sdg" aria-label="UN Sustainable Development Goals">
            {SDGS.map((goal) => (
              <li key={goal.code}>
                <span>SDG {goal.code}</span>
                <p>{goal.title}</p>
              </li>
            ))}
          </ul>
        </div>
        <div className="sl-footer__meta">
          <p>Built for IDEALIZE 2026 — Agent Kernel Mini-Competition</p>
          <p>
            <a href={GITHUB_REPO_URL} target="_blank" rel="noopener noreferrer">
              GitHub repository
            </a>
          </p>
        </div>
      </div>
      <p className="sl-footer__powered ds-mono">
        Powered by{" "}
        <a href={AGENT_KERNEL_URL} target="_blank" rel="noopener noreferrer">
          Agent Kernel
        </a>
      </p>
    </footer>
  );
}
