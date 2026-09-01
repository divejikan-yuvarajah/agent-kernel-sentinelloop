import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { normalizeRisk } from "@ds/colors";

import { notifications } from "../../data/demoData";
import { useDemoMode } from "../../demo/useDemoMode";

type Props = {
  count?: number;
};

export function NotificationCenter({ count }: Props) {
  const [demo] = useDemoMode();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const items = demo ? notifications.slice(0, 6) : [];
  const unread = count ?? items.length;

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  return (
    <div className="sl-notify" ref={rootRef}>
      <button
        type="button"
        className="sl-notify__bell"
        aria-label={unread ? `${unread} unread operational alerts` : "No unread alerts"}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        {unread > 0 ? <span className="sl-notify__count" aria-hidden="true" /> : null}
        <span aria-hidden="true">!</span>
      </button>
      {open ? (
        <div className="sl-notify__panel" id={panelId} role="dialog" aria-label="Notification center">
          <p className="sl-notify__heading">Notifications</p>
          {items.length === 0 ? (
            <p className="ds-empty">No alerts in this session</p>
          ) : (
            <ul>
              {items.map((item) => (
                <li key={item.id} className={`sl-notify__item sl-notify__item--${normalizeRisk(item.severity)}`}>
                  <strong>{item.title}</strong>
                  <span>{item.body}</span>
                  <span className="ds-mono">{item.time}</span>
                </li>
              ))}
            </ul>
          )}
          <Link to="/notifications" className="sl-notify__all" onClick={() => setOpen(false)}>
            Open notification center
          </Link>
        </div>
      ) : null}
    </div>
  );
}
