"""Unified incident intake.

Telegram, dashboard manual entry, and future channels enter the same
orchestrator pipeline: intake → incident → risk (calculate_risk) →
guidance → coordination → database.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from integrations.inbound import InboundMedia, NormalizedInboundMessage
from integrations.incident_orchestrator import IncidentOrchestrator, OrchestrationResult, get_incident_orchestrator
from services.demo_mode import (
    ALLOWED_PHOTO_SUFFIXES,
    ALLOWED_PHOTO_TYPES,
    HAZARD_CATEGORIES,
    PIPELINE_VERSION,
    demo_mode_enabled,
)

log = logging.getLogger("sentinelloop.intake_service")

SOURCE_TELEGRAM = "telegram"
SOURCE_MANUAL = "manual"
SOURCE_QR = "qr"
SOURCE_SANDBOX = "sandbox"
VALID_SOURCES = frozenset({SOURCE_TELEGRAM, SOURCE_MANUAL, SOURCE_QR, SOURCE_SANDBOX})


def compose_manual_report_text(
    description: str,
    *,
    category: str,
    location: str,
    people_exposed: int,
    is_active: bool,
    injury_reported: bool,
    equipment_involved: str | None = None,
) -> str:
    body = (description or "").strip()
    lines = [
        body,
        "",
        f"Category: {category}",
        f"Location: {location}",
        f"People exposed: {people_exposed}",
        f"Currently active: {'yes' if is_active else 'no'}",
        f"Injury reported: {'yes' if injury_reported else 'no'}",
    ]
    equipment = (equipment_involved or "").strip()
    if equipment:
        lines.insert(4, f"Equipment involved: {equipment}")
    return "\n".join(lines).strip()


def validate_manual_incident(
    *,
    description: str | None,
    category: str | None,
    location: str | None,
    people_exposed: object,
    photo_filename: str | None = None,
    photo_content_type: str | None = None,
    is_active: object = True,
    injury_reported: object = False,
) -> str | None:
    text = (description or "").strip()
    if not text:
        return "Description is required before creating incident"
    if len(text) < 10:
        return "Description must be at least 10 characters"
    if not (location or "").strip():
        return "Location is required before creating incident"
    if not (category or "").strip():
        return "Category is required before creating incident"
    wanted = (category or "").strip()
    allowed = {item.lower() for item in HAZARD_CATEGORIES}
    if wanted.lower() not in allowed:
        return "Category must be one of the listed hazard types"
    try:
        people = int(people_exposed)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "People exposed must be a number"
    if people < 0:
        return "People exposed must be a number"
    if is_active is None:
        return "Active-hazard status is required"
    if injury_reported is None:
        return "Injury status is required"
    if photo_content_type:
        mime = photo_content_type.strip().lower()
        if mime not in ALLOWED_PHOTO_TYPES:
            return "Image must be jpg, png, or webp"
    if photo_filename:
        suffix = ""
        if "." in photo_filename:
            suffix = "." + photo_filename.rsplit(".", 1)[-1].lower()
        if suffix and suffix not in ALLOWED_PHOTO_SUFFIXES:
            return "Image must be jpg, png, or webp"
    return None


def build_manual_message(
    *,
    raw_text: str,
    created_by: str | None = None,
    category: str | None = None,
    location: str | None = None,
    people_exposed: int | None = None,
    is_active: bool | None = None,
    injury_reported: bool | None = None,
    equipment_involved: str | None = None,
    photo: InboundMedia | None = None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedInboundMessage:
    reporter = (created_by or "").strip()
    is_anonymous = not reporter
    officer = reporter or None
    sender_id = f"dashboard:{reporter}" if reporter else "dashboard:anonymous"
    media = photo
    message_type = "image" if media is not None else "text"
    extra = dict(metadata or {})
    extra.update(
        {
            "category": category,
            "location": location,
            "people_exposed": people_exposed,
            "is_active": is_active,
            "injury_reported": injury_reported,
            "equipment_involved": (equipment_involved or "").strip() or None,
            "is_anonymous": is_anonymous,
        }
    )
    return NormalizedInboundMessage(
        provider_message_id=f"manual:{uuid4()}",
        sender_id=sender_id,
        message_type=message_type,
        text=raw_text,
        media=media,
        received_at=datetime.now(timezone.utc),
        supported=True,
        input_channel=SOURCE_MANUAL,
        input_method="dashboard",
        created_by=officer,
        pipeline_version=PIPELINE_VERSION,
        source_metadata=extra,
    )


def decode_photo(
    photo_base64: str | None,
    *,
    filename: str | None = None,
    content_type: str | None = None,
) -> InboundMedia | None:
    if not photo_base64:
        return None
    raw = photo_base64.strip()
    if "," in raw and raw.lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        content = base64.b64decode(raw, validate=False)
    except Exception:
        return None
    if not content:
        return None
    mime = (content_type or "image/jpeg").strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    return InboundMedia(
        media_id=f"manual-photo:{uuid4()}",
        mime_type=mime,
        filename=filename or "hazard.jpg",
        content=content,
        size_bytes=len(content),
    )


async def process_incident_input(
    source: str,
    raw_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    message: NormalizedInboundMessage | dict[str, Any] | None = None,
    orchestrator: IncidentOrchestrator | None = None,
) -> OrchestrationResult:
    """Normalize an inbound report and run the shared incident pipeline."""
    channel = (source or SOURCE_TELEGRAM).strip().lower() or SOURCE_TELEGRAM
    if channel == SOURCE_QR:
        channel = SOURCE_TELEGRAM
    orch = orchestrator or _default_orchestrator()
    inbound = message
    if inbound is None:
        if channel == SOURCE_MANUAL:
            meta = dict(metadata or {})
            inbound = build_manual_message(
                raw_text=(raw_text or "").strip(),
                created_by=str(meta.get("created_by") or meta.get("reporter_name") or "") or None,
                category=str(meta.get("category") or "") or None,
                location=str(meta.get("location") or "") or None,
                people_exposed=meta.get("people_exposed"),
                is_active=meta.get("is_active"),
                injury_reported=meta.get("injury_reported"),
                equipment_involved=str(meta.get("equipment_involved") or "") or None,
                photo=meta.get("photo"),
                metadata=meta,
            )
        else:
            inbound = NormalizedInboundMessage(
                provider_message_id=f"{channel}:{uuid4()}",
                sender_id=str((metadata or {}).get("sender_id") or f"{channel}:unknown"),
                message_type="text",
                text=raw_text,
                received_at=datetime.now(timezone.utc),
                supported=True,
                input_channel=channel,
                input_method=str((metadata or {}).get("input_method") or "") or None,
            )
    if isinstance(inbound, dict):
        inbound = NormalizedInboundMessage.model_validate(inbound)
    if not inbound.input_channel:
        inbound.input_channel = channel
    if channel == SOURCE_MANUAL:
        inbound.input_channel = SOURCE_MANUAL
        inbound.input_method = inbound.input_method or "dashboard"
        inbound.pipeline_version = inbound.pipeline_version or PIPELINE_VERSION
    if channel == SOURCE_SANDBOX:
        inbound.input_channel = SOURCE_SANDBOX
        inbound.input_method = inbound.input_method or "sandbox"
        inbound.pipeline_version = inbound.pipeline_version or PIPELINE_VERSION
        meta = dict(inbound.source_metadata or {})
        meta["input_channel"] = SOURCE_SANDBOX
        meta["is_sandbox"] = True
        inbound.source_metadata = meta
    log.info("incident_intake source=%s channel=%s", source, inbound.input_channel)
    dispatch = getattr(orch, "process_inbound_message", None) or orch.process_incoming_telegram_message
    return await dispatch(inbound)


def _default_orchestrator() -> IncidentOrchestrator:
    if demo_mode_enabled():
        from services.demo_pipeline import build_demo_orchestrator

        return build_demo_orchestrator()
    return get_incident_orchestrator()
