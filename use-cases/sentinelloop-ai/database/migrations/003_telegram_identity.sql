-- Additive Telegram identity columns. Does not alter the original five-table contract.

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT;

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS telegram_user_id TEXT;

ALTER TABLE incidents
    ADD COLUMN IF NOT EXISTS telegram_message_id TEXT;

CREATE INDEX IF NOT EXISTS incidents_telegram_chat_id_idx
    ON incidents (telegram_chat_id);
