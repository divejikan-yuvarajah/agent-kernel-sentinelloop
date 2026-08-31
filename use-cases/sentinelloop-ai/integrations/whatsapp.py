"""Future WhatsApp integration boundary.

Inbound webhook events, worker identity, text, images, voice metadata,
and outbound worker responses. Implementation will wrap
AgentWhatsAppRequestHandler (subclass for idempotency and outbound send).
Do not invent a WhatsAppIntegration.send_message API.

Implementation is intentionally deferred to a later build phase.
"""
