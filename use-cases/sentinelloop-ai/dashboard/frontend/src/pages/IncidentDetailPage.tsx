import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  AppShell,
  Badge,
  Button,
  EvidenceViewer,
  IncidentTimeline,
  Modal,
  Panel,
  RiskAssessmentPanel,
  RiskIndicator,
  SafetyStatusBadge,
  StatusIndicator,
} from "@ds/index";
import type { EvidenceItem, RiskAssessment, TimelineEvent } from "@ds/types";
import { normalizeRisk } from "@ds/colors";

import { fetchAuditExport, fetchIncident, type AuditExport, type IncidentDetail } from "../api/client";
import { AuditTrailView } from "../components/AuditTrailView";
import { slackThread } from "../data/demoData";
import { useDemoMode } from "../demo/useDemoMode";

function downloadAudit(audit: AuditExport) {
  const blob = new Blob([JSON.stringify(audit, null, 2)], { type: "application/json" });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = `SentinelLoop_Audit_${audit.incident_information.incident_id}.json`;
  link.click();
  URL.revokeObjectURL(href);
}

export function IncidentDetailPage() {
  const { incidentId = "" } = useParams();
  const [demo] = useDemoMode();
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [auditOpen, setAuditOpen] = useState(false);
  const [audit, setAudit] = useState<AuditExport | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);

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
  }, [incidentId, demo]);

  function exportAudit() {
    setAuditOpen(true);
    setAuditLoading(true);
    setAuditError(null);
    setAudit(null);
    fetchAuditExport(incidentId)
      .then((payload) => {
        setAudit(payload);
        setAuditError(null);
      })
      .catch((err: Error) => setAuditError(err.message))
      .finally(() => setAuditLoading(false));
  }

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
      stage: item.stage,
    })) ?? [];

  return (
    <AppShell title={detail?.incident_id ?? "Incident"} operationalStatus={detail?.status ?? "OPEN"}>
      <p className="ds-page-lead">
        <Link to="/incidents">Incident Management</Link>
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
                <Badge title="Multiple workers reported this same hazard">
                  {detail.duplicates.duplicate_count} REPORTS
                </Badge>
              ) : null}
              {detail.source === "QR_TAGGED" ? <Badge title="Location verified by QR scan">QR Tagged</Badge> : null}
              <SafetyStatusBadge status={detail.safety_status} />
            </div>
            <p style={{ margin: "16px 0 0" }}>{detail.location}</p>
            {detail.assigned_team ? (
              <p className="ds-mono" style={{ margin: "4px 0 0" }}>
                Assigned: {detail.assigned_team}
                {detail.assigned_officer ? ` · ${detail.assigned_officer}` : ""}
              </p>
            ) : null}
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
            {detail.original_text ? (
              <Panel title="Worker report" style={{ marginBottom: 24 }}>
                <p className="ds-metric__label">Original</p>
                <p style={{ margin: "4px 0 12px" }}>{detail.original_text}</p>
                <p className="ds-metric__label">Translation</p>
                <p style={{ margin: "4px 0 12px" }}>{detail.translated_text}</p>
                <p className="ds-mono">Language: {detail.language ?? detail.reporter.language ?? "—"}</p>
              </Panel>
            ) : null}
            {detail.equipment || detail.people_exposed != null ? (
              <Panel title="AI extraction" style={{ marginBottom: 24 }}>
                <p>Hazard: {detail.category}</p>
                <p>Location: {detail.location}</p>
                <p>Equipment: {detail.equipment ?? "—"}</p>
                <p>People exposed: {detail.people_exposed ?? "—"}</p>
                <p>Active: {detail.hazard_active ? "Yes" : "No"}</p>
                <p>Injury: {detail.injury ? "Yes" : "No"}</p>
              </Panel>
            ) : null}
            <div className="ds-toolbar">
              <Button variant="ghost" data-testid="audit-export" onClick={exportAudit}>
                Export audit trail
              </Button>
            </div>
            <h3 style={{ marginTop: 8 }}>AI decision timeline</h3>
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
            {detail.severity != null && detail.likelihood != null ? (
              <Panel title="Risk matrix">
                <p>Severity: {detail.severity}</p>
                <p>Likelihood: {detail.likelihood}</p>
                <p>Score: {detail.risk.risk_score}</p>
                <p>Level: {detail.risk.risk_level}</p>
                <p style={{ marginTop: 12, color: "var(--chalk-muted)" }}>{detail.risk.risk_explanation}</p>
              </Panel>
            ) : null}
            {detail.safety ? (
              <Panel title="AI Decision Safety Panel">
                <p>Risk Level: {detail.safety.risk_level ?? "Unknown"}</p>
                <p>Human Review: {detail.safety.human_review}</p>
                <p>Guidance: {detail.safety.guidance}</p>
                <p>Closure: {detail.safety.closure}</p>
                {detail.safety.auto_close_disabled ? (
                  <p className="ds-mono">Human approval required according to SPEC.md</p>
                ) : null}
                <div className="ds-toolbar">
                  <Button disabled={detail.safety.auto_close_disabled} title="Auto Close is blocked for High/Critical">
                    Auto Close
                  </Button>
                </div>
                <h3 style={{ marginTop: 16 }}>Generated Guidance</h3>
                <p>Matched Knowledge Base: {detail.safety.guidance_verification.knowledge_base_file ?? "—"}</p>
                <p>Supported Lines: {detail.safety.guidance_verification.supported_lines ?? "—"}</p>
                <p>Hallucination Check: {detail.safety.guidance_verification.hallucination_check ?? "—"}</p>
                <h3 style={{ marginTop: 16 }}>Guardrail Timeline</h3>
                {detail.safety.timeline.map((event, index) => (
                  <p key={`${event.title}-${index}`} className="ds-mono">
                    {event.timestamp ? event.timestamp.slice(11, 16) : "--:--"} {event.title}
                    {event.detail ? ` · ${event.detail}` : ""}
                  </p>
                ))}
              </Panel>
            ) : null}
            {detail.incident_id === slackThread.incident ? (
              <Panel title={`Slack · ${slackThread.channel}`}>
                <p className="ds-mono">
                  {detail.assigned_team} · {slackThread.actions.join(" · ")}
                </p>
                <ul className="ds-slack">
                  {slackThread.messages.map((message) => (
                    <li key={message.text}>
                      <strong>{message.author}</strong>
                      <span>{message.text}</span>
                    </li>
                  ))}
                </ul>
                <p>
                  <Link to="/coordination">Open coordination</Link>
                </p>
              </Panel>
            ) : null}
            <Panel title="Evidence">
              <EvidenceViewer items={evidence} />
            </Panel>
          </div>
        </div>
      )}
      <Modal
        open={auditOpen}
        title="Incident audit trail"
        className="ds-modal--audit"
        onClose={() => setAuditOpen(false)}
      >
        {auditLoading ? (
          <p className="ds-empty" role="status">
            Generating audit trail...
          </p>
        ) : auditError ? (
          <p className="ds-empty" role="alert">
            {auditError}
          </p>
        ) : audit ? (
          <AuditTrailView audit={audit} onDownload={() => downloadAudit(audit)} />
        ) : null}
        <div className="ds-toolbar" style={{ marginTop: 16, marginBottom: 0 }}>
          <Button variant="quiet" onClick={() => setAuditOpen(false)}>
            Close
          </Button>
        </div>
      </Modal>
    </AppShell>
  );
}
