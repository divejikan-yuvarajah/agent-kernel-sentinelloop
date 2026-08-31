"""Future integration tests.

Intended coverage: WhatsApp inbound event path; Slack alert path;
duplicate webhook idempotency; WhatsApp/Slack/Supabase failure must not
look like success.

No live Meta/Slack calls. No assertions in this scaffold.
"""
