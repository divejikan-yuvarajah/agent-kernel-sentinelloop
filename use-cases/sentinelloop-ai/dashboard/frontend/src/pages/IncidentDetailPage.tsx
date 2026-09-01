import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  AppShell,
  ChannelBadge,
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
import type { EvidenceItem, RiskAssessment, TimelineEvent, PredictionItem } from "@ds/types";
import { normalizeRisk } from "@ds/colors";

import { fetchAuditExport, fetchIncident, fetchPredictions, type AuditExport, type IncidentDetail } from "../api/client";
import { AuditTrailView } from "../components/AuditTrailView";
import { EvidenceImage } from "../components/EvidenceImage";
import { slackThread } from "../data/demoData";
import { evidenceRecord, incidentPair, visionAnalysis } from "../data/demoImages";
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
  const [warning, setWarning] = useState<PredictionItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchIncident(incidentId)
      .then((payload) => {
        if (cancelled) return;
        setDetail(payload);
        setError(null);
        return fetchPredictions()
          .catch(() => null)
          .then((forecast) => {
            if (cancelled || !forecast) return;
            const match =
              forecast.predictions.find(
                (item) =>
                  item.location.toLowerCase() === (payload.location || "").toLowerCase() &&
                  item.category.toLowerCase() === (payload.category || "").toLowerCase(),
              ) ||
              forecast.predictions.find((item) => item.location.toLowerCase() === (payload.location || "").toLowerCase());
            setWarning(match ?? null);
          });
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
  const pair = incidentPair(detail?.incident_id, detail?.category);
  const vision = visionAnalysis(detail?.incident_id, detail?.category);
  const evidence: EvidenceItem[] =
    detail?.evidence.map((item) => {
      const known = evidenceRecord(item.evidence_id);
      const after = item.stage === "verification";
      return {
        id: item.evidence_id,
        label: item.label ?? "Evidence",
        source: item.source ?? "unknown",
        timestamp: item.uploaded_at ?? "",
        kind: item.has_image ? "image" : item.content_kind === "voice" || item.kind === "voice" ? "voice" : "file",
        stage: item.stage,
        uploaded_by: item.uploaded_by,
        channel: item.source,
        imageSrc: item.has_image || item.kind === "image" ? known?.src || (after ? pair.after : pair.before) : null,
      };
    }) ?? [];

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
              <ChannelBadge
                channel={detail.input_channel || detail.reporter.source_channel}
                elapsed={detail.elapsed_time}
              />
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
            {warning ? (
              <Panel className="ds-warning-panel" title="Future Risk Warning">
                <p>This location has a recurring hazard pattern.</p>
                <p>
                  Probability of repeat incident: {warning.risk_level === "High" || warning.trend === "increasing" ? "High" : "Medium"}
                </p>
                <p>Recommended: {warning.recommendation}</p>
              </Panel>
            ) : null}
            {detail.original_text ? (
              <Panel title="Worker report" style={{ marginBottom: 24 }}>
                <p className="ds-metric__label">Original</p>
                <p style={{ margin: "4px 0 12px" }}>{detail.original_text}</p>
                <p className="ds-metric__label">Translation</p>
                <p style={{ margin: "4px 0 12px" }}>{detail.translated_text}</p>
                <p className="ds-mono">Language: {detail.language ?? detail.reporter.language ?? "—"}</p>
              </Panel>
            ) : null}
            <Panel title="Worker Evidence" style={{ marginBottom: 24 }}>
              <p>
                Reported by: {detail.is_anonymous ? "Anonymous Worker" : "Worker"}
              </p>
              <p>
                Channel:{" "}
                {(detail.input_channel || detail.reporter.source_channel) === "telegram"
                  ? "Source: Telegram 💬"
                  : detail.input_channel || detail.reporter.source_channel || "Workshop"}
              </p>
              <p className="ds-mono">AI Processing: Completed</p>
              <EvidenceImage src={pair.before} alt={detail.title || "Worker evidence"} ratio="16/9" />
            </Panel>
            <Panel title="Incident Evidence Gallery" style={{ marginBottom: 24 }}>
              <p className="ds-metric__label">Original Evidence · AI Analysis · Resolution Evidence</p>
              <div className="ds-before-after ds-before-after--triple">
                <article>
                  <p className="ds-metric__label">Original Evidence</p>
                  <EvidenceImage src={pair.before} alt="Original worker image" />
                </article>
                <article>
                  <p className="ds-metric__label">AI Analysis</p>
                  <EvidenceImage src={pair.before} alt="AI analysis of hazard image" />
                  <p className="ds-mono">{(detail.vision?.hazard_category || vision.hazard)} suggestion</p>
                </article>
                <article>
                  <p className="ds-metric__label">Resolution Evidence</p>
                  <EvidenceImage src={pair.after} alt="Resolution image" />
                </article>
              </div>
            </Panel>
            <Panel title="Before / After Safety Comparison" style={{ marginBottom: 24 }}>
              <div className="ds-before-after">
                <article>
                  <p className="ds-metric__label">Before</p>
                  <EvidenceImage src={pair.before} alt="Hazard image" />
                  <p>Risk: High</p>
                </article>
                <article>
                  <p className="ds-metric__label">After</p>
                  <EvidenceImage src={pair.after} alt="Fixed image" />
                  <p>Risk: Closed</p>
                </article>
              </div>
            </Panel>
            <Panel title="AI Image Analysis" style={{ marginBottom: 24 }}>
              <p className="ds-metric__label">Uploaded Image → AI Observation → Final Classification</p>
              <EvidenceImage src={pair.before} alt="Worker photo" ratio="16/9" />
              <p>
                <strong>AI Suggestion</strong> {detail.vision?.hazard_category || vision.hazard} Hazard
              </p>
              {(() => {
                const conf = detail.vision?.confidence != null ? Math.round(detail.vision.confidence * 100) : vision.confidence;
                const band = detail.vision?.confidence_band || (conf >= 90 ? "high" : conf >= 60 ? "medium" : "low");
                const label = band === "high" ? "High Confidence" : band === "medium" ? "Medium Confidence" : "Low Confidence";
                return (
                  <p>
                    Confidence: {conf}%{" "}
                    <span className={`ds-confidence ds-confidence--${band}`}>{label}</span>
                  </p>
                );
              })()}
              <p>Observed:</p>
              <ul className="ds-vision">
                {(detail.vision?.observations?.length ? detail.vision.observations : vision.objects).map((item) => (
                  <li key={item}>✓ {item}</li>
                ))}
              </ul>
              <p>
                <strong>Final Category:</strong> {detail.vision?.final_category || detail.category}
              </p>
              <p className="ds-mono">Suggestion only. Worker text and human review remain in control.</p>
            </Panel>
            {detail.included_in_handovers && detail.included_in_handovers.length > 0 ? (
              <Panel title="Included in Handover" style={{ marginBottom: 24 }}>
                {detail.included_in_handovers.map((item) => (
                  <p key={item.handover_id}>
                    This incident was highlighted in:
                    <br />
                    {item.shift_label} Handover
                    <br />
                    {item.generated_at ? new Date(item.generated_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) : "—"}
                  </p>
                ))}
              </Panel>
            ) : null}
            {detail.voice_report ? (
              <Panel title="🎤 Voice Report" style={{ marginBottom: 24 }}>
                <p>
                  Language: {detail.voice_report.language_name || detail.voice_report.language || detail.language || "—"}
                </p>
                <p>Duration: {detail.voice_report.duration_seconds ?? "—"} seconds</p>
                <p>Transcript: {detail.voice_report.transcript ? `"${detail.voice_report.transcript}"` : "—"}</p>
                {detail.voice_report.confidence_label ? (
                  <p>Voice Understanding: {detail.voice_report.confidence_label}</p>
                ) : null}
                <p>AI Processing: {detail.voice_report.processing_status || "Completed"}</p>
                <div style={{ marginTop: 16 }}>
                  <p style={{ marginBottom: 8 }}>▶ Play Voice Report</p>
                  {detail.voice_report.playback_url ? (
                    <audio controls src={detail.voice_report.playback_url} preload="none">
                      Voice report
                    </audio>
                  ) : (
                    <p className="ds-mono">
                      00:{String(Math.round(detail.voice_report.duration_seconds ?? 18)).padStart(2, "0")}
                    </p>
                  )}
                  <p style={{ marginTop: 8 }}>Uploaded by: {detail.voice_report.uploaded_by || "Worker"}</p>
                </div>
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
              <EvidenceViewer
                items={evidence}
                renderImage={(item) =>
                  item.kind === "image" ? (
                    <EvidenceImage src={item.imageSrc} alt={item.label} />
                  ) : (
                    <div className="ds-photo ds-photo--empty">Voice</div>
                  )
                }
              />
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
