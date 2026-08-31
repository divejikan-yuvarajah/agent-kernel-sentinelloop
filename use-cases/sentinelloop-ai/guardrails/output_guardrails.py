"""Future output validation.

Structured extraction checks, model-output sanity, valid risk ranges, and
tool-result consistency. PostHook sees only the final user-facing reply,
not inner risk_agent handoffs — persist official risk from the tool.

Implementation is intentionally deferred to a later build phase.
"""
