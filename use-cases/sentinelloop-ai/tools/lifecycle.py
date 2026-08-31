"""Future incident lifecycle policy.

Allowed status transitions, close-only-after-verification, reopen on
worker rejection, and reject stale/concurrent invalid updates against
the latest durable status.

Implementation is intentionally deferred to a later build phase.
"""
