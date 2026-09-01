import { Panel } from "@ds/index";

type Voice = {
  duration_seconds?: number | null;
  language_name?: string | null;
  language?: string | null;
  transcript?: string | null;
  playback_url?: string | null;
  uploaded_by?: string;
  confidence_label?: string | null;
  processing_status?: string;
};

type Props = {
  originalText?: string | null;
  translatedText?: string | null;
  language?: string | null;
  voiceReport?: Voice | null;
  hasImageAssist?: boolean;
};

export function WorkerReportPanel({
  originalText,
  translatedText,
  language,
  voiceReport,
  hasImageAssist = false,
}: Props) {
  return (
    <Panel title="Original Report" className="ii-worker">
      {originalText ? (
        <>
          <p className="ii-kicker">Worker message</p>
          <p className="ii-worker__text">{originalText}</p>
        </>
      ) : (
        <p className="ds-empty">No original worker message on record</p>
      )}
      {translatedText ? (
        <>
          <p className="ii-kicker">English translation</p>
          <p className="ii-worker__text">{translatedText}</p>
        </>
      ) : null}
      {language ? <p className="ds-mono">Language: {language}</p> : null}

      {voiceReport ? (
        <div className="ii-worker__voice">
          <h3>🎤 Voice Report</h3>
          <p>Language: {voiceReport.language_name || voiceReport.language || language || "—"}</p>
          <p>Duration: {voiceReport.duration_seconds ?? "—"} seconds</p>
          {voiceReport.transcript ? <p>Transcript: “{voiceReport.transcript}”</p> : null}
          {voiceReport.confidence_label ? <p>Voice Understanding: {voiceReport.confidence_label}</p> : null}
          <p>AI Processing: {voiceReport.processing_status || "Completed"}</p>
          <p className="ii-kicker">Play Audio</p>
          {voiceReport.playback_url ? (
            <audio controls src={voiceReport.playback_url} preload="none">
              Voice report
            </audio>
          ) : (
            <p className="ds-mono">00:{String(Math.round(voiceReport.duration_seconds ?? 18)).padStart(2, "0")}</p>
          )}
          <p>Uploaded by: {voiceReport.uploaded_by || "Worker"}</p>
        </div>
      ) : null}

      {hasImageAssist ? (
        <p className="ii-worker__image-assist">
          <strong>Image Assisted Report</strong> — a hazard photo helped classify this case.
        </p>
      ) : null}
    </Panel>
  );
}
