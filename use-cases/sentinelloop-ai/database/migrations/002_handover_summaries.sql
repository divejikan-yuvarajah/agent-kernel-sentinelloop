-- Shift handover briefings. Does not alter incidents, evidence, risk, assignments, or updates.
-- UUID + timestamptz follow SPEC.md incident table conventions.

CREATE TABLE IF NOT EXISTS handover_summaries (
    handover_id UUID PRIMARY KEY,
    shift_label TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    summary_text TEXT NOT NULL,
    open_incident_count INTEGER NOT NULL DEFAULT 0,
    critical_open_count INTEGER NOT NULL DEFAULT 0,
    generated_by TEXT,
    slack_posted BOOLEAN NOT NULL DEFAULT FALSE,
    payload JSONB
);

CREATE INDEX IF NOT EXISTS handover_summaries_generated_at_idx
    ON handover_summaries (generated_at DESC);

ALTER TABLE handover_summaries ENABLE ROW LEVEL SECURITY;
