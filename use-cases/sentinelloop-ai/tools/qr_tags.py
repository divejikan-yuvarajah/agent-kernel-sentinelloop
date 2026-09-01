"""Shared QR location-tag parsing.

Used by intake, dashboard analytics, and the QR generator. Does not import
agents or mutate incidents.

Two worker prefixes exist:

- ``SLQR ...`` — original structured tag (unchanged; parsed by intake).
- ``[LOC:location|equipment]`` — intake prefix mapped from a Telegram
  ``/start <qr_id>`` deep link generated from ``locations.yaml``.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel

log = logging.getLogger("sentinelloop.qr_tags")

SOURCE_QR_TAGGED = "QR_TAGGED"

LOC_START_RE = re.compile(r"^\[LOC:", re.IGNORECASE)
LOC_VALID_RE = re.compile(
    r"^\[LOC:\s*([^\[\]\|]+?)\s*\|\s*([^\[\]\|]+?)\s*\]",
    re.IGNORECASE,
)
UNSAFE_VALUE_RE = re.compile(r"(https?://|javascript:|data:|<script|</|[\x00-\x08\x0b\x0c\x0e-\x1f])", re.IGNORECASE)
MAX_FIELD_LENGTH = 200
MAX_ENCODED_MESSAGE_LENGTH = 240


class LocTagParse(BaseModel):
    present: bool = False
    valid: bool = False
    location: str | None = None
    equipment: str | None = None
    human_text: str = ""
    encoded_message: str | None = None


def sanitize_qr_field(value: str, *, field_max: int = MAX_FIELD_LENGTH) -> str:
    text = (value or "").replace("\r\n", "\n").strip()
    text = re.sub(r"\s+", " ", text)
    if not text:
        raise ValueError("empty QR field")
    if len(text) > field_max:
        raise ValueError("QR field too long")
    if UNSAFE_VALUE_RE.search(text):
        raise ValueError("unsafe QR field")
    if "|" in text or "[" in text or "]" in text:
        raise ValueError("QR field contains reserved characters")
    return text


def format_loc_prefix(location: str, equipment: str) -> str:
    loc = sanitize_qr_field(location)
    eq = sanitize_qr_field(equipment)
    message = f"[LOC:{loc}|{eq}]"
    if len(message) > MAX_ENCODED_MESSAGE_LENGTH:
        raise ValueError("QR payload exceeds maximum length")
    return message


def parse_loc_tag(text: str, *, field_max: int = MAX_FIELD_LENGTH) -> LocTagParse:
    """Parse a leading ``[LOC:location|equipment]`` tag.

    Invalid or incomplete tags are not stripped. Callers should treat those
    messages as ordinary worker text.
    """
    original = text or ""
    stripped = original.lstrip("\ufeff").lstrip()
    if not stripped:
        return LocTagParse(human_text=original)
    if not LOC_START_RE.match(stripped):
        return LocTagParse(human_text=original)

    match = LOC_VALID_RE.match(stripped)
    if not match:
        log.info("invalid_location_tag_detected")
        return LocTagParse(present=True, valid=False, human_text=original)

    try:
        location = sanitize_qr_field(match.group(1), field_max=field_max)
        equipment = sanitize_qr_field(match.group(2), field_max=field_max)
    except ValueError:
        log.info("invalid_location_tag_detected")
        return LocTagParse(present=True, valid=False, human_text=original)

    rest = stripped[match.end() :].lstrip()
    return LocTagParse(
        present=True,
        valid=True,
        location=location,
        equipment=equipment,
        human_text=rest,
        encoded_message=format_loc_prefix(location, equipment),
    )


def extract_qr_origin(original_message: str | None) -> dict[str, str | bool | None]:
    """Dashboard helper: detect a stored Telegram body that began as a QR report."""
    parsed = parse_loc_tag(original_message or "")
    if parsed.valid:
        return {
            "source": SOURCE_QR_TAGGED,
            "location_verified": True,
            "qr_location": parsed.location,
            "qr_equipment": parsed.equipment,
            "format": "loc_tag",
        }
    stripped = (original_message or "").lstrip("\ufeff").lstrip()
    if stripped.upper().startswith("SLQR") or stripped.upper().startswith("<SLQR"):
        return {
            "source": SOURCE_QR_TAGGED,
            "location_verified": True,
            "qr_location": None,
            "qr_equipment": None,
            "format": "slqr",
        }
    return {
        "source": None,
        "location_verified": False,
        "qr_location": None,
        "qr_equipment": None,
        "format": None,
    }


QrFormat = Literal["loc_tag", "slqr"]
