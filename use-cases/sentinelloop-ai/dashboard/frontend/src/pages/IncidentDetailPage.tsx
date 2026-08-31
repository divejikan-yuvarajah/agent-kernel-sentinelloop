import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  AppShell,
  Badge,
  EvidenceViewer,
  IncidentTimeline,
  Panel,
  RiskAssessmentPanel,
  RiskIndicator,
  StatusIndicator,
} from "@ds/index";
import type { EvidenceItem, RiskAssessment, TimelineEvent } from "@ds/types";
import { normalizeRisk } from "@ds/colors";

import { fetchIncident, type IncidentDetail } from "../api/client";

export function IncidentDetailPage() {
  const { incidentId = "" } = useParams();
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchIncident(incidentId)
      .then((payload) => {
        if (cancelled) return;
        setDetail(payload);
        setError(null);
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setDetail(null);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [incidentId]);

  const assessment: RiskAssessment | null = detail
    ? {
        level: normalizeRisk(detail.risk.risk_level ?? "MEDIUM"),
        score: detail.risk.risk_score ?? 0,
        confidence: Math.round((detail.risk.ai_confidence ?? 0) * 100),
        hazards: detail.risk.detected_hazards,
        reasoning: detail.risk.reasoning_summary || detail.risk.risk_explanation || "No reasoning on record.",
      }
    : null;
  const events: TimelineEvent[] =
    detail?.timeline.map((event) => ({
      timestamp: event.timestamp ?? "",
      title: event.title,
      detail: event.detail ?? undefined,
    })) ?? [];
  const evidence: EvidenceItem[] =
    detail?.evidence.map((item) => ({
      id: item.evidence_id,
      label: item.label ?? "Evidence",
      source: item.source ?? "unknown",
      timestamp: item.uploaded_at ?? "",
      kind: item.has_image ? "image" : "file",
    })) ?? [];

  return (
    <AppShell title={detail?.incident_id ?? "Incident"} operationalStatus={detail?.status ?? "OPEN"}>
      <p className="ds-page-lead">
        <Link to="/incidents">Active incidents</Link>
        {" / "}
        <span className="ds-mono">{incidentId}</span>
      </p>
      {loading ? (
        <p className="ds-empty">Loading incident intelligence…</p>
      ) : error || !detail || !assessment ? (
        <p className="ds-empty" role="alert">
          {error === "incident not found" ? "Incident not found." : error || "Incident not found."}
        </p>
      ) : (
        <div className="ds-grid ds-grid--split">
          <Panel title={detail.title ?? detail.incident_id}>
            <div className="ds-meta-row" style={{ marginTop: 0 }}>
              <StatusIndicator status={detail.status} />
              <RiskIndicator level={assessment.level} score={assessment.score} />
              <span className="ds-mono">{detail.elapsed_time}</span>
              {detail.duplicates.duplicate_count > 1 ? (
                <Badge>Duplicate ×{detail.duplicates.duplicate_count}</Badge>
              ) : null}
              {detail.source === "QR_TAGGED" ? <Badge title="Location verified by QR scan">QR Tagged</Badge> : null}
            </div>
            <p style={{ margin: "16px 0 0" }}>{detail.location}</p>
            {detail.location_verified ? (
              <p className="ds-verified ds-mono">
                Location verified
                {detail.qr_equipment ? ` · ${detail.qr_equipment}` : ""}
              </p>
            ) : null}
            <p style={{ margin: "8px 0 0", color: "var(--chalk-muted)" }}>{detail.description}</p>
            <p style={{ margin: "8px 0 24px", color: "var(--chalk-muted)" }}>
              Reporter {detail.reporter.reporter_id}
              {detail.assigned_officer ? ` · Assigned to ${detail.assigned_officer}` : " · Unassigned"}
            </p>
            <IncidentTimeline events={events} />
            {detail.duplicates.linked_incidents.length > 0 ? (
              <p style={{ marginTop: 24, fontSize: "var(--font-size-sm)", color: "var(--chalk-muted)" }}>
                Linked:{" "}
                {detail.duplicates.linked_incidents.map((item) => item.incident_id).join(", ")}
                {detail.duplicates.duplicate_similarity_score != null
                  ? ` · similarity ${detail.duplicates.duplicate_similarity_score}`
                  : ""}
              </p>
            ) : null}
          </Panel>
          <div className="ds-grid">
            <RiskAssessmentPanel assessment={assessment} />
            <Panel title="Evidence">
              <EvidenceViewer items={evidence} />
            </Panel>
          </div>
        </div>
      )}
    </AppShell>
  );
}
