import { Link } from "react-router-dom";

import {
  DASHBOARD_PATH,
  HERO_STATS,
  SANDBOX_PATH,
  TELEGRAM_BOT_HANDLE,
  TELEGRAM_BOT_URL,
} from "../constants";
import { LoopHero } from "./LoopHero";

export function Hero() {
  return (
    <header className="sl-hero">
      <div className="sl-hero__orb" aria-hidden="true" />
      <div className="sl-wrap sl-hero__grid">
        <div className="sl-hero__copy">
          <p className="sl-hero__kicker sl-kicker">Workplace safety · Sinhala · Tamil · English</p>
          <h1 className="sl-hero__headline">
            Report danger in seconds.
            <br />
            Prevent the next accident.
          </h1>
          <p className="sl-hero__lede">
            SentinelLoop AI turns a two-second Telegram message into a tracked, accountable safety response — in
            Sinhala, Tamil, or English.
          </p>
          <div className="sl-hero__actions">
            <Link className="ds-btn" to={SANDBOX_PATH}>
              Try SentinelLoop Live
            </Link>
            <a className="ds-btn ds-btn--ghost" href={TELEGRAM_BOT_URL} target="_blank" rel="noopener noreferrer">
              Message the bot on Telegram
            </a>
            <Link className="ds-btn ds-btn--ghost" to={DASHBOARD_PATH}>
              View live dashboard
            </Link>
          </div>
          <p className="sl-hero__bot ds-mono">{TELEGRAM_BOT_HANDLE}</p>
          <ul className="sl-hero__stats" aria-label="Product facts">
            {HERO_STATS.map((stat) => (
              <li key={stat.label}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </li>
            ))}
          </ul>
        </div>
        <LoopHero />
      </div>
    </header>
  );
}
