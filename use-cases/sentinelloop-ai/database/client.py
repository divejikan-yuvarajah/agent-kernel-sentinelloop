"""Supabase client factory for SentinelLoop durable persistence.

Reads SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY from the environment.
The service-role key bypasses Row Level Security. Use it only on the
server. Never log it, never send it to the dashboard frontend, never
return it from an API.

This module is not an Agent Kernel session store.
"""

from __future__ import annotations

import logging
import os

from supabase import Client, create_client

from database.exceptions import DatabaseConfigError

log = logging.getLogger("sentinelloop.database")

_REQUIRED = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")

_client: Client | None = None

DEFAULT_EVIDENCE_BUCKET = "evidence"


def _missing_config() -> list[str]:
    return [name for name in _REQUIRED if not os.environ.get(name)]


def create_supabase_client() -> Client:
    """Build a new sync Client. Does not cache. Never logs secret values."""
    missing = _missing_config()
    if missing:
        raise DatabaseConfigError("Missing required Supabase configuration: " + ", ".join(missing))
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    log.info("Initializing Supabase client")
    return create_client(url, key)


def get_supabase_client() -> Client:
    """Return a process-wide cached client. Call reset_supabase_client in tests."""
    global _client
    if _client is None:
        _client = create_supabase_client()
    return _client


def reset_supabase_client() -> None:
    """Drop the cached client so the next get_supabase_client() rebuilds it."""
    global _client
    _client = None


def evidence_bucket_name() -> str:
    """Storage bucket for evidence. Defaults to `evidence` per the build guide."""
    return os.environ.get("SUPABASE_STORAGE_BUCKET") or DEFAULT_EVIDENCE_BUCKET
