"""Demo image file validation. Does not change upload APIs or storage schema."""

from __future__ import annotations

from pathlib import Path

ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".svg"})
REJECTED_EXTENSIONS = frozenset({".exe", ".bat", ".cmd", ".js", ".html", ".php", ""})
MAX_IMAGE_BYTES = 16 * 1024 * 1024
_UNSAFE_CHARS = '<>:"|?*\\'


def sanitize_filename(name: str) -> str:
    raw = Path(str(name or "").replace("\\", "/")).name.strip()
    cleaned = "".join("_" if ch in _UNSAFE_CHARS or ord(ch) < 32 else ch for ch in raw)
    cleaned = cleaned.lstrip(".")
    return cleaned or "untitled.jpg"


def validate_image_file(name: str, content: bytes | None = None) -> dict[str, str | int | bool]:
    """Return a validation result. Invalid types are rejected; missing bytes are allowed for path checks."""
    filename = sanitize_filename(name)
    suffix = Path(filename).suffix.lower()
    size = len(content or b"")
    if suffix in REJECTED_EXTENSIONS or suffix not in ALLOWED_EXTENSIONS:
        return {"ok": False, "reason": "invalid_type", "filename": filename, "size": size}
    if content is not None and size > MAX_IMAGE_BYTES:
        return {"ok": False, "reason": "too_large", "filename": filename, "size": size}
    if content is not None and size == 0:
        return {"ok": False, "reason": "empty", "filename": filename, "size": size}
    return {"ok": True, "reason": "accepted", "filename": filename, "size": size}
