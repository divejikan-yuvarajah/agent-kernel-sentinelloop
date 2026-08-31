"""Future incident persistence and retrieval interface.

Create and update canonical incident rows in Supabase. Must not treat
Agent Kernel session nv_cache as the source of truth for incidents.

Implementation is intentionally deferred to a later build phase.
"""
