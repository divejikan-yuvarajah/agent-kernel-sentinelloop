"""Future safety invariants.

Deterministic escalation must apply; models must not downgrade below the
mandatory minimum; guidance must not be fabricated; incidents must not
auto-close unsafely. Prompt-injection content is data, not instructions.

Implementation is intentionally deferred to a later build phase.
"""
