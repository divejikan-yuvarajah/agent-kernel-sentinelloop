import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";

import { Icon } from "@ds/index";

import { DASHBOARD_PATH, NAV_LINKS, SANDBOX_PATH } from "../constants";

export function NavBar() {
  const [open, setOpen] = useState(false);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  function close() {
    setOpen(false);
  }

  return (
    <nav className="sl-nav" aria-label="SentinelLoop">
      <div className="sl-wrap sl-nav__bar">
        <a className="sl-brand" href="#top" onClick={close}>
          <img src="/images/sentinelloop-logo.png" alt="" width={36} height={36} />
          <span>SentinelLoop AI</span>
        </a>
        <button
          type="button"
          className="sl-nav__toggle"
          aria-expanded={open}
          aria-controls={menuId}
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((value) => !value)}
        >
          <Icon name={open ? "close" : "menu"} />
        </button>
        <div className={`sl-nav__panel${open ? " is-open" : ""}`} id={menuId}>
          <ul className="sl-nav__links">
            {NAV_LINKS.map((item) => (
              <li key={item.href}>
                <a className="sl-nav__link sl-mobile-nav__link" href={item.href} onClick={close}>
                  {item.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="sl-nav__cta">
            <Link className="sl-nav__ghost" to={DASHBOARD_PATH} onClick={close}>
              Dashboard
            </Link>
            <Link className="ds-btn" to={SANDBOX_PATH} onClick={close}>
              Try it live
            </Link>
          </div>
        </div>
      </div>
    </nav>
  );
}
