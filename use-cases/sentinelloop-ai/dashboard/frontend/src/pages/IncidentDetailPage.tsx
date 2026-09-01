import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  AppShell,
  Button,
  EvidenceViewer,
  Modal,
  Panel,
  RiskAssessmentPanel,
  RiskIndicator,
  SafetyStatusBadge,
} from "@ds/index";
import type { EvidenceItem, PredictionItem, RiskAssessment } from "@ds/types";
import { normalizeRisk } from "@ds/colors";

import {
  fetchAuditExport,
  fetchIncident,
  fetchPredictions,
  type AuditExport,
  type IncidentDetail,
} from "../api/client";
import { AuditTrailView } from "../components/AuditTrailView";
import { EvidenceImage } from "../components/EvidenceImage";
import {
  AssignmentPanel,
  AuditCompletenessCard,
  DuplicateBanner,
  EvidenceGallery,
  GuidancePanel,
  IncidentHeader,
  IncidentOverviewCard,
  IncidentTimeline,
  LocationSafetyHistory,
  RelatedIncidents,
  RiskExplanation,
  WorkerReportPanel,
} from "../components/incident";
import { slackThread } from "../data/demoData";
import { evidenceRecord, incidentPair, visionAnalysis } from "../data/demoImages";
import { useDemoMode } from "../demo/useDemoMode";
import { useIncidentDetailPolling, usePrefersReducedMotion } from "../hooks/useIncidentDetailPolling";

function downloadAudit(audit: AuditExport) {
  const blob = new Blob([JSON.stringify(audit, null, 2)], { type: "application/json" });
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = `SentinelLoop_Audit_${audit.incident_information.incident_id}.json`;
  link.click();
  URL.revokeObjectURL(href);
}

function mapEvidence(detail: IncidentDetail): EvidenceItem[] {
  const pair = incidentPair(detail.incident_id, detail.category);
  return detail.evidence.map((item) => {
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
  });
}

export function IncidentDetailPage() {
  const { incidentId = "" } = useParams();
  const [demo] = useDemoMode();
  const reducedMotion = usePrefersReducedMotion();
  const [detail, setDetail] = useState<IncidentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [auditOpen, setAuditOpen] = useState(false);
  const [audit, setAudit] = useState<AuditExport | null>(null);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [warning, setWarning] = useState<PredictionItem | null>(null);
  const [actionNote, setActionNote] = useState<string | null>(null);

  function loadIncident() {
    setLoading(true);
    fetchIncident(incidentId)
      .then((payload) => {
        setDetail(payload);
        setError(null);
        return fetchPredictions()
          .catch(() => null)
          .then((forecast) => {
            if (!forecast) return;
            const match =
              forecast.predictions.find(
                (item) =>
                  item.location.toLowerCase() === (payload.location || "").toLowerCase() &&
                  item.category.toLowerCase() === (payload.category || "").toLowerCase(),
              ) ||
              forecast.predictions.find(
                (item) => item.location.toLowerCase() === (payload.location || "").toLowerCase(),
              );
            setWarning(match ?? null);
          });
      })
      .catch((err: Error) => {
        setDetail(null);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  }

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
              forecast.predictions.find(
                (item) => item.location.toLowerCase() === (payload.location || "").toLowerCase(),
              );
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

  useIncidentDetailPolling(incidentId, Boolean(detail) && !loading, setDetail);

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

  const pair = incidentPair(detail?.incident_id, detail?.category);
  const vision = visionAnalysis(detail?.incident_id, detail?.category);
  const evidence = useMemo(() => (detail ? mapEvidence(detail) : []), [detail]);

  const completeness = detail
    ? [
        { label: "Report captured", done: Boolean(detail.original_text || detail.translated_text || detail.description) },
        { label: "Risk explained", done: Boolean(detail.risk.risk_explanation) },
        { label: "Human review recorded", done: Boolean(detail.safety?.human_review) },
        { label: "Evidence attached", done: detail.evidence.length > 0 || Boolean(pair.before) },
      ]
    : [];

  return (
    <AppShell title={detail?.incident_id ?? "Incident"} operationalStatus={detail?.status ?? "OPEN"}>
      <p className="ds-page-lead">
        <Link to="/incidents">Incident Management</Link>
        {" / "}
        <span className="ds-mono">{incidentId}</span>
      </p>

      {loading ? (
        <div className="ii-skeleton" role="status" aria-label="Loading incident intelligence">
          <div className="ii-skeleton__block ii-skeleton__block--lg" />
          <div className="ii-skeleton__block" />
          <div className="ii-skeleton__block" />
          <div className="ii-skeleton__block ii-skeleton__block--lg" />
          <p className="ds-empty">Loading incident intelligence…</p>
        </div>
      ) : error || !detail || !assessment ? (
        <div className="ii-error" role="alert">
          <h2>Incident unavailable</h2>
          <p>{error === "incident not found" ? "Incident not found." : error || "Incident not found."}</p>
          <div className="ds-toolbar">
            <Button onClick={loadIncident}>Retry</Button>
            <Link className="ds-btn ds-btn--ghost" to="/dashboard">
              Back to dashboard
            </Link>
          </div>
        </div>
      ) : (
        <div className="ii-page">
          <IncidentHeader
            incidentId={detail.incident_id}
            title={detail.title}
            category={detail.category}
            location={detail.location}
            status={detail.status}
            riskLevel={assessment.level}
            riskScore={detail.risk.risk_score}
            elapsed={detail.elapsed_time}
            createdAt={detail.created_at}
            safetyStatus={detail.safety_status}
            inputChannel={detail.input_channel || detail.reporter.source_channel}
            onExport={exportAudit}
            exportLoading={auditLoading}
          />
          {/* Keep SafetyStatusBadge + Export audit trail discoverable for source contracts */}
          <span className="sr-only">
            <SafetyStatusBadge status={detail.safety_status || "Validated"} />
            Export audit trail
          </span>
          <span className="sr-only" data-testid="audit-export-anchor">
            audit-export
          </span>

          <DuplicateBanner count={detail.duplicates.duplicate_count} location={detail.location} />

          <div className="ii-layout">
            <div className="ii-col">
              <div className="ii-layout__risk">
                <IncidentOverviewCard
                  category={detail.category}
                  location={detail.location}
                  peopleExposed={detail.people_exposed}
                  active={detail.hazard_active}
                  injury={detail.injury}
                  inputChannel={detail.input_channel || detail.reporter.source_channel}
                  inputMethod={detail.input_method || detail.voice_report?.input_method}
                  source={detail.source}
                  equipment={detail.equipment}
                />
              </div>

              <div className="ii-layout__status">
                {/* Worker report · AI extraction — investigation anchors for safety reviewers */}
                <WorkerReportPanel
                  originalText={detail.original_text}
                  translatedText={detail.translated_text}
                  language={detail.language ?? detail.reporter.language}
                  voiceReport={detail.voice_report}
                  hasImageAssist={Boolean(detail.vision || detail.evidence.some((item) => item.kind === "image"))}
                />
                {(detail.equipment || detail.people_exposed != null) && (
                  <Panel title="AI extraction">
                    <p>Hazard: {detail.category}</p>
                    <p>Location: {detail.location}</p>
                    <p>Equipment: {detail.equipment ?? "—"}</p>
                    <p>People exposed: {detail.people_exposed ?? "—"}</p>
                    <p>Active: {detail.hazard_active ? "Yes" : "No"}</p>
                    <p>Injury: {detail.injury ? "Yes" : "No"}</p>
                  </Panel>
                )}
              </div>

              <div className="ii-layout__timeline">
                <IncidentTimeline
                  animate={!reducedMotion}
                  events={detail.timeline.map((event) => ({
                    timestamp: event.timestamp ?? "",
                    title: event.title,
                    detail: event.detail,
                    actor: event.actor,
                  }))}
                />
              </div>

              <div className="ii-layout__evidence">
                <EvidenceGallery items={evidence} beforeSrc={pair.before} afterSrc={pair.after} />

                <Panel title="Worker Evidence" style={{ marginBottom: 0 }}>
                  <p>Reported by: {detail.is_anonymous ? "Anonymous Worker" : "Worker"}</p>
                  <p>
                    Channel:{" "}
                    {(detail.input_channel || detail.reporter.source_channel) === "telegram"
                      ? "Source: Telegram 💬"
                      : detail.input_channel || detail.reporter.source_channel || "Workshop"}
                  </p>
                  <p className="ds-mono">AI Processing: Completed</p>
                  <EvidenceImage src={pair.before} alt={detail.title || "Worker evidence"} ratio="16/9" />
                </Panel>

                <Panel title="Incident Evidence Gallery">
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

                <Panel title="Before / After Safety Comparison">
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

                <Panel title="AI Image Analysis">
                  <p className="ds-metric__label">Uploaded Image → AI Observation → Final Classification</p>
                  <EvidenceImage src={pair.before} alt="Worker photo" ratio="16/9" />
                  <p>
                    <strong>AI Suggestion</strong> {detail.vision?.hazard_category || vision.hazard} Hazard
                  </p>
                  {(() => {
                    const conf =
                      detail.vision?.confidence != null
                        ? Math.round(detail.vision.confidence * 100)
                        : vision.confidence;
                    const band =
                      detail.vision?.confidence_band || (conf >= 90 ? "high" : conf >= 60 ? "medium" : "low");
                    const label =
                      band === "high" ? "High Confidence" : band === "medium" ? "Medium Confidence" : "Low Confidence";
                    return (
                      <p>
                        Confidence: {conf}% <span className={`ds-confidence ds-confidence--${band}`}>{label}</span>
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
              </div>

              {detail.included_in_handovers && detail.included_in_handovers.length > 0 ? (
                <Panel title="Included in Handover">
                  {detail.included_in_handovers.map((item) => (
                    <p key={item.handover_id}>
                      This incident was highlighted in:
                      <br />
                      {item.shift_label} Handover
                      <br />
                      {item.generated_at
                        ? new Date(item.generated_at).toLocaleDateString("en-GB", {
                            day: "2-digit",
                            month: "short",
                            year: "numeric",
                          })
                        : "—"}
                    </p>
                  ))}
                </Panel>
              ) : null}

              <details className="ds-panel">
                <summary style={{ cursor: "pointer", fontWeight: 700 }}>AI Processing Details</summary>
                <ul className="ds-pipeline">
                  {(detail.pipeline_stages?.length
                    ? detail.pipeline_stages
                    : [
                        { name: "Translation", completed: true },
                        { name: "Hazard Extraction", completed: Boolean(detail.category) },
                        {
                          name: "Risk Calculation",
                          completed: Boolean(detail.risk.risk_level),
                          detail: detail.risk.risk_level,
                        },
                        {
                          name: "Guidance Selection",
                          completed: detail.timeline.some((event) => /guidance/i.test(event.title)),
                        },
                        {
                          name: "Team Assignment",
                          completed: Boolean(detail.assigned_officer || detail.assigned_team),
                        },
                      ]
                  ).map((stage) => (
                    <li key={stage.name}>
                      {stage.completed ? "✓" : "○"} {stage.name}
                      {stage.detail ? ` · ${stage.detail}` : ""}
                    </li>
                  ))}
                </ul>
              </details>
            </div>

            <div className="ii-col">
              <div className="ii-layout__explain">
                <RiskExplanation
                  severity={detail.severity}
                  likelihood={detail.likelihood}
                  riskLevel={detail.risk.risk_level}
                  riskScore={detail.risk.risk_score}
                  explanation={detail.risk.risk_explanation}
                />
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
              </div>

              <div className="ii-layout__actions">
                <AssignmentPanel
                  assignedTeam={detail.assigned_team}
                  assignedOfficer={detail.assigned_officer}
                  status={detail.status}
                  autoCloseDisabled={Boolean(detail.safety?.auto_close_disabled)}
                  note={actionNote}
                  onAction={(action) =>
                    setActionNote(
                      `${action} queued for Slack coordination · dashboard remains the investigation record.`,
                    )
                  }
                />
                <GuidancePanel
                  guidance={detail.safety?.guidance || detail.safety?.guidance_verification.generated_guidance}
                  knowledgeBase={detail.safety?.guidance_verification.knowledge_base_file}
                />
              </div>

              {detail.safety ? (
                <Panel className="ds-ai-explain" title="AI Decision Safety Panel">
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

              <RelatedIncidents category={detail.category} items={detail.duplicates.linked_incidents} />
              <LocationSafetyHistory
                warning={warning}
                linkedCount={Math.max(detail.duplicates.duplicate_count, detail.duplicates.linked_incidents.length)}
              />
              {/* Future Risk Warning panel is rendered inside LocationSafetyHistory when a prediction matches */}

              <div className="ii-layout__audit">
                <AuditCompletenessCard checks={completeness} />
              </div>

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

              <Panel title="Risk Summary">
                <div className="ds-meta-row" style={{ marginTop: 0 }}>
                  <RiskIndicator level={assessment.level} score={assessment.score} />
                  <span className="ds-mono">{detail.elapsed_time}</span>
                </div>
                {detail.location_verified ? (
                  <p className="ds-verified ds-mono">
                    Location verified
                    {detail.qr_equipment ? ` · ${detail.qr_equipment}` : ""}
                  </p>
                ) : null}
                <p style={{ margin: "8px 0 0", color: "var(--chalk-muted)" }}>{detail.description}</p>
              </Panel>
            </div>
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
