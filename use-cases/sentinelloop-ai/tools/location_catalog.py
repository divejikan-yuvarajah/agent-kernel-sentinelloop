"""Load and validate ``locations.yaml`` for QR poster generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tools.qr_tags import MAX_FIELD_LENGTH, format_loc_prefix, sanitize_qr_field

_ID_SAFE = re.compile(r"[^A-Z0-9]+")


class LocationConfigError(ValueError):
    """locations.yaml is missing, malformed, or internally inconsistent."""


class LocationEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    location: str
    equipment: str
    area_code: str | None = None
    building: str | None = None
    floor: str | None = None
    department: str | None = None
    safety_zone: str | None = None
    emergency_contact: str | None = None
    qr_id: str | None = None
    version: int = 1

    @field_validator("location", "equipment", mode="before")
    @classmethod
    def _required_name(cls, value: Any) -> str:
        if value is None or str(value).strip() == "":
            raise ValueError("required")
        return sanitize_qr_field(str(value), field_max=MAX_FIELD_LENGTH)

    @field_validator(
        "area_code",
        "building",
        "floor",
        "department",
        "safety_zone",
        "emergency_contact",
        "qr_id",
        mode="before",
    )
    @classmethod
    def _clean(cls, value: Any) -> Any:
        if value is None or value == "":
            return None if value == "" else value
        return sanitize_qr_field(str(value), field_max=MAX_FIELD_LENGTH)

    @field_validator("version", mode="before")
    @classmethod
    def _version(cls, value: Any) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("version must be an integer") from exc
        if number < 1:
            raise ValueError("version must be >= 1")
        return number

    @model_validator(mode="after")
    def _assign_qr_id(self) -> LocationEntry:
        format_loc_prefix(self.location, self.equipment)
        if self.qr_id:
            ident = self.qr_id.upper()
        else:
            ident = _default_qr_id(self.area_code, self.location, self.equipment, self.version)
        object.__setattr__(self, "qr_id", ident)
        return self


def _default_qr_id(area_code: str | None, location: str, equipment: str, version: int) -> str:
    if area_code:
        slug = _ID_SAFE.sub("-", area_code.upper()).strip("-")
    else:
        slug = _ID_SAFE.sub("-", f"{location}-{equipment}".upper()).strip("-")
    ident = f"SNT-{slug}"
    if version > 1 and not ident.endswith(f"-V{version}"):
        ident = f"{ident}-V{version}"
    return ident


def load_locations(path: Path) -> list[LocationEntry]:
    if not path.exists():
        raise LocationConfigError(f"locations file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise LocationConfigError("invalid locations YAML") from exc
    if not isinstance(raw, dict) or "locations" not in raw:
        raise LocationConfigError("locations.yaml must contain a top-level 'locations' list")
    rows = raw.get("locations")
    if not isinstance(rows, list) or not rows:
        raise LocationConfigError("locations must be a non-empty list")
    entries: list[LocationEntry] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise LocationConfigError(f"location entry {index} is not a mapping")
        try:
            entry = LocationEntry.model_validate(row)
        except Exception as exc:
            raise LocationConfigError(f"location entry {index} is invalid: {exc}") from exc
        assert entry.qr_id is not None
        if entry.qr_id in seen:
            raise LocationConfigError(f"duplicate QR ID: {entry.qr_id}")
        seen.add(entry.qr_id)
        entries.append(entry)
    return entries
