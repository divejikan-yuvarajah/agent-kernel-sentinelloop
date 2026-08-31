"""Future incident status transition enforcement.

Reject invalid durable updates (for example CLOSED from IN_PROGRESS).
Complements tools/lifecycle.py; persistence must validate latest state.

Implementation is intentionally deferred to a later build phase.
"""
