import { Link } from "react-router-dom";

import { AppShell, Card, RiskIndicator } from "@ds/index";
import { normalizeRisk } from "@ds/colors";

import { notifications } from "../data/demoData";
import { incidentThumbnail } from "../data/demoImages";
import { EvidenceImage } from "../components/EvidenceImage";
import { useDemoMode } from "../demo/useDemoMode";

export function NotificationsPage() {
  const [demo] = useDemoMode();
  return (
    <AppShell title="Notification Center" operationalStatus="OPEN" notificationCount={demo ? notifications.length : 0}>
      <p className="ds-page-lead">Operational alerts for the duty officer. Critical items stay at the top of the list.</p>
      {demo ? (
        <div className="ds-grid">
          {notifications.map((item) => (
            <Card key={item.id} variant="activity-card">
              <EvidenceImage
                src={incidentThumbnail(item.body.includes("INC-2026-00421") ? "INC-2026-00421" : item.body.includes("00420") ? "INC-2026-00420" : "INC-2026-00415")}
                alt=""
                ratio="16/9"
              />
              <div className="ds-meta-row" style={{ marginTop: 12 }}>
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
        <p className="ds-empty">No unread alerts. All safety issues are currently resolved.</p>
      )}
    </AppShell>
  );
}
