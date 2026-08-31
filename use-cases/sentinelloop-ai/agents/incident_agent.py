"""SentinelLoop incident extraction agent.

Responsible for converting worker reports into structured incident facts
and asking only safety-critical clarification questions. Missing facts
stay unknown; they are never coerced to false.

Implementation is intentionally deferred to a later build phase.
"""
