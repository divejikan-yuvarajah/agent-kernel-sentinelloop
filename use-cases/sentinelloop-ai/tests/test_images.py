"""Demo image catalog, before/after links, and file validation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from seed_demo_images import EVIDENCE_FILES, IMAGE_DIR, INCIDENT_FILES, LOCATION_FILES, seed  # noqa: E402

from tools.image_security import sanitize_filename, validate_image_file  # noqa: E402


def test_invalid_executables_rejected():
    result = validate_image_file("payload.exe", b"MZ")
    assert result["ok"] is False
    assert result["reason"] == "invalid_type"


def test_unknown_files_rejected():
    result = validate_image_file("notes.txt", b"hello")
    assert result["ok"] is False


def test_allowed_image_types_accepted():
    for name in ("panel.jpg", "after.PNG", "scan.webp"):
        result = validate_image_file(name, b"\x89PNG")
        assert result["ok"] is True
        assert result["filename"] == sanitize_filename(name)


def test_sanitize_filename_strips_paths():
    assert sanitize_filename(r"..\\..\\secrets.exe") == "secrets.exe"
    assert sanitize_filename("ok photo.jpg") == "ok photo.jpg"


def test_empty_image_rejected():
    assert validate_image_file("empty.jpg", b"")["ok"] is False


def test_missing_image_result_is_explicit():
    missing = IMAGE_DIR / "does-not-exist.jpg"
    assert missing.exists() is False


def test_seed_is_idempotent_and_links_catalog():
    first = seed()
    second = seed()
    assert first["locations"] == second["locations"]
    assert first["incidents"] == second["incidents"]
    assert first["evidence"] == second["evidence"]
    assert first["avatars"] >= 5
    assert first["locations"] == len(LOCATION_FILES)
    assert first["incidents"] == len(INCIDENT_FILES)
    assert first["evidence"] == len(EVIDENCE_FILES)
    assert (IMAGE_DIR / "electrical_panel_damage.jpg").exists()
    assert (IMAGE_DIR / "electrical_panel_repaired.jpg").exists()
    assert (IMAGE_DIR / "chemical_spill.jpg").exists()
    assert (IMAGE_DIR / "chemical_area_cleaned.jpg").exists()
    assert (IMAGE_DIR / "avatar-kasun.svg").exists()
