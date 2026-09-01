-- Additive dashboard / multi-channel intake columns. Does not alter the original five-table contract.

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS input_method TEXT;

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS created_by TEXT;

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS source_metadata JSONB;

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS pipeline_version TEXT;

CREATE INDEX IF NOT EXISTS incidents_input_method_idx
    ON incidents (input_method);

CREATE INDEX IF NOT EXISTS incidents_created_by_idx
    ON incidents (created_by);
