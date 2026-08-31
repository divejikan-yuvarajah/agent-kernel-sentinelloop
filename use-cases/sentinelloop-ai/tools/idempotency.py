"""Webhook / provider-event idempotency.

Deduplicate WhatsApp and Slack deliveries by stable provider message or
event ids. This is not semantic incident-duplicate detection.
"""

from __future__ import annotations

from typing import Any


def event_key(provider: str, provider_message_id: str) -> str:
    """Stable idempotency key. Never use message text."""
    return f"{provider.strip().lower()}:{provider_message_id.strip()}"


class EventIdempotencyStore:
    """Process-local store. Inject a fake in tests. No extra database table."""

    def __init__(self) -> None:
        self._results: dict[str, dict[str, Any]] = {}
        self._in_flight: set[str] = set()

    def get(self, key: str) -> dict[str, Any] | None:
        return self._results.get(key)

    def begin(self, key: str) -> bool:
        """Mark an event in-flight. Return False if already seen or in flight."""
        if key in self._results or key in self._in_flight:
            return False
        self._in_flight.add(key)
        return True

    def complete(self, key: str, result: dict[str, Any]) -> dict[str, Any]:
        self._in_flight.discard(key)
        stored = dict(result)
        self._results[key] = stored
        return stored

    def abandon(self, key: str) -> None:
        """Allow a later retry after a crash before completion."""
        self._in_flight.discard(key)
