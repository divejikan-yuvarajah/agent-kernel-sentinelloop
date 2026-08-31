"""Future webhook idempotency helpers.

Deduplicate external WhatsApp and Slack events using provider message or
event ids so retries do not create duplicate incidents, evidence, Slack
alerts, or lifecycle transitions.

Implementation is intentionally deferred to a later build phase.
"""
