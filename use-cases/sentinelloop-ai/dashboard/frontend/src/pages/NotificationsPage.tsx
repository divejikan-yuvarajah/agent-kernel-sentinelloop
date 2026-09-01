import { Link } from "react-router-dom";

import { AppShell, Card, RiskIndicator } from "@ds/index";
import { normalizeRisk } from "@ds/colors";

import { notifications } from "../data/demoData";
import { notificationAllowed, useOperatorPrefs } from "../demo/operatorPrefs";
import { useDemoMode } from "../demo/useDemoMode";

export function NotificationsPage() {
  const [demo] = useDemoMode();
  const [prefs] = useOperatorPrefs();
  const visible = demo ? notifications.filter((item) => notificationAllowed(item, prefs)) : [];

  return (
    <AppShell title="Notification Center" operationalStatus="OPEN" notificationCount={visible.length}>
      <p className="ds-page-lead">
        Operational alerts for the duty officer. Critical items stay at the top of the list. Alert types follow Settings
        for this browser.
      </p>
      {demo ? (
        visible.length > 0 ? (
          <div className="ds-grid">
            {visible.map((item) => (
              <Card
                key={item.id}
                variant="activity-card"
                className={
                  item.severity === "CRITICAL"
                    ? "ds-notify-critical"
                    : item.severity === "HIGH"
                      ? "ds-notify-warning"
                      : "ds-notify-info"
                }
              >
                <div className="ds-meta-row">
                  <RiskIndicator level={normalizeRisk(item.severity)} score={item.severity === "CRITICAL" ? 25 : 12} />
                  <span className="ds-mono">{item.time}</span>
                </div>
                <h3 style={{ margin: "12px 0 8px", fontSize: "var(--font-size-md)" }}>{item.title}</h3>
                <p>{item.body}</p>
                {item.body.includes("INC-2026-00421") ? (
                  <p>
                    <Link to="/incidents/INC-2026-00421">Open INC-2026-00421</Link>
                  </p>
                ) : null}
              </Card>
            ))}
          </div>
        ) : (
          <p className="ds-empty">
            No alerts match the types enabled in Settings. Turn a category back on to see it here.
          </p>
        )
      ) : (
        <p className="ds-empty">No unread alerts. All safety issues are currently resolved.</p>
      )}
    </AppShell>
  );
}
