"""Deterministic approved-guidance loader.

Hazard category is mapped to a whitelist of local markdown files. Worker text
and model output must never construct filesystem paths.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

KNOWLEDGE_BASE_VERSION = "1.0"
KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parents[1] / "knowledge_base"
GENERAL_FILE = "general_hazards.md"
MAX_ACTION_LINE_CHARS = 180

GUIDANCE_FILE_MAP = {
    "electrical": "electrical_safety.md",
    "fire/smoke": "fire_safety.md",
    "chemical": "chemical_safety.md",
    "machine": "general_hazards.md",
    "slip/trip": "general_hazards.md",
    "missing PPE": "general_hazards.md",
    "structural": "general_hazards.md",
    "unsafe behaviour": "general_hazards.md",
    "other": "general_hazards.md",
}

APPROVED_FILENAMES = frozenset(GUIDANCE_FILE_MAP.values())

SOURCE_PREFIX = {
    "electrical_safety.md": "electrical",
    "fire_safety.md": "fire",
    "chemical_safety.md": "chemical",
    "general_hazards.md": "general",
}

_CATEGORY_ALIASES = {
    "electrical": "electrical",
    "electric": "electrical",
    "electricity": "electrical",
    "fire": "fire/smoke",
    "smoke": "fire/smoke",
    "fire/smoke": "fire/smoke",
    "fire-smoke": "fire/smoke",
    "fire_smoke": "fire/smoke",
    "chemical": "chemical",
    "machine": "machine",
    "machinery": "machine",
    "slip": "slip/trip",
    "trip": "slip/trip",
    "slip/trip": "slip/trip",
    "ppe": "missing PPE",
    "missing ppe": "missing PPE",
    "structural": "structural",
    "unsafe behaviour": "unsafe behaviour",
    "unsafe behavior": "unsafe behaviour",
    "other": "other",
}


class GuidanceConfigError(RuntimeError):
    """Approved knowledge base is missing or unsafe to use."""


class GuidanceLine(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    text: str
    is_footer: bool = False


class GuidancePack(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str
    filename: str
    category_fallback: bool = False
    lines: list[GuidanceLine]
    footer: GuidanceLine | None = None

    @property
    def action_lines(self) -> list[GuidanceLine]:
        return [line for line in self.lines if not line.is_footer]


def normalize_hazard_category(category: str | None) -> str:
    if category is None or str(category).strip() == "":
        return ""
    raw = str(category).strip().lower()
    return _CATEGORY_ALIASES.get(raw, raw)


def get_guidance_filename(category: str | None) -> tuple[str, bool]:
    """Return (approved filename, whether general fallback was used)."""
    normalized = normalize_hazard_category(category)
    if normalized in GUIDANCE_FILE_MAP:
        return GUIDANCE_FILE_MAP[normalized], False
    return GENERAL_FILE, True


def resolve_guidance_path(filename: str, kb_dir: Path | None = None) -> Path:
    if filename not in APPROVED_FILENAMES:
        raise GuidanceConfigError("unapproved knowledge-base filename")
    directory = (kb_dir or KNOWLEDGE_BASE_DIR).resolve()
    path = (directory / filename).resolve()
    if path.parent != directory:
        raise GuidanceConfigError("knowledge-base path traversal blocked")
    return path


@lru_cache(maxsize=16)
def _read_text(path_str: str) -> str:
    return Path(path_str).read_text(encoding="utf-8")


def load_guidance_document(category: str | None, *, kb_dir: Path | None = None) -> str:
    filename, _fallback = get_guidance_filename(category)
    path = resolve_guidance_path(filename, kb_dir)
    if not path.is_file():
        raise GuidanceConfigError(f"missing knowledge-base file {filename}")
    return _read_text(str(path))


def parse_guidance_lines(content: str, filename: str) -> list[GuidanceLine]:
    """Load immediate worker actions for live guidance.

    Extra ``##`` sections (site regulations, duties, prohibitions) stay in the
    knowledge-base files and PDFs. They are not sent as the worker action pack.
    Files without section headings still treat every bullet as an action.
    """
    prefix = SOURCE_PREFIX.get(filename, "general")
    actions: list[str] = []
    footer: str | None = None
    collecting = True
    seen_section = False
    for raw in content.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            if not seen_section:
                seen_section = True
                heading = line[3:].strip().lower()
                collecting = heading.startswith("immediate") or heading in {"rules", "actions"}
            else:
                collecting = False
            continue
        if line.startswith("#"):
            continue
        if line.startswith(("- ", "* ")):
            if collecting:
                actions.append(line[2:].strip())
            continue
        footer = line
    records: list[GuidanceLine] = []
    for index, text in enumerate(actions, start=1):
        records.append(GuidanceLine(id=f"{prefix}_{index}", text=text, is_footer=False))
    if footer:
        records.append(GuidanceLine(id=f"{prefix}_footer", text=footer, is_footer=True))
    return records


def get_safety_footer(content: str, filename: str) -> str | None:
    for line in parse_guidance_lines(content, filename):
        if line.is_footer:
            return line.text
    return None


def load_guidance_lines(category: str | None, *, kb_dir: Path | None = None) -> list[str]:
    pack = load_guidance_pack(category, kb_dir=kb_dir)
    texts = [line.text for line in pack.action_lines]
    if pack.footer:
        texts.append(pack.footer.text)
    return texts


def _pack_from_filename(
    filename: str,
    normalized: str,
    category_fallback: bool,
    kb_dir: Path | None,
) -> GuidancePack:
    path = resolve_guidance_path(filename, kb_dir)
    if not path.is_file():
        raise GuidanceConfigError(f"missing knowledge-base file {filename}")
    content = _read_text(str(path))
    records = parse_guidance_lines(content, filename)
    actions = [line for line in records if not line.is_footer]
    footer = next((line for line in records if line.is_footer), None)
    if not actions or footer is None:
        raise GuidanceConfigError("knowledge-base file is empty or missing a trained-personnel line")
    return GuidancePack(
        category=normalized or "other",
        filename=filename,
        category_fallback=category_fallback or not normalized,
        lines=records,
        footer=footer,
    )


def load_guidance_pack(category: str | None, *, kb_dir: Path | None = None) -> GuidancePack:
    """Load the approved pack for a category. Falls back to general if mapped file is unusable."""
    normalized = normalize_hazard_category(category)
    filename, category_fallback = get_guidance_filename(category)
    try:
        return _pack_from_filename(filename, normalized, category_fallback, kb_dir)
    except GuidanceConfigError:
        if filename != GENERAL_FILE:
            return _pack_from_filename(GENERAL_FILE, normalized, True, kb_dir)
        raise


def clear_guidance_cache() -> None:
    _read_text.cache_clear()


def extract_risk_level(mapping: dict[str, Any]) -> str | None:
    if mapping.get("risk_level"):
        return str(mapping["risk_level"])
    nested = mapping.get("risk")
    if isinstance(nested, dict) and nested.get("level"):
        return str(nested["level"])
    return None
