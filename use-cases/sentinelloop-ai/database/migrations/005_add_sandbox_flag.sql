-- Additive sandbox isolation flag. Does not alter the original five-table contract.

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS is_sandbox BOOLEAN DEFAULT false;

CREATE INDEX IF NOT EXISTS incidents_is_sandbox_idx
    ON incidents (is_sandbox)
    WHERE is_sandbox = true;
