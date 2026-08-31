"""Idempotent Horizon Engineering Workshop demo image seeder.

Writes avatars and verifies the local photo library under
dashboard/frontend/public/images. Does not touch Supabase schema or APIs.

Usage (from use-cases/sentinelloop-ai):

    uv run python scripts/seed_demo_images.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.image_security import validate_image_file  # noqa: E402

IMAGE_DIR = ROOT / "dashboard" / "frontend" / "public" / "images"

LOCATION_FILES = (
    "main_workshop_floor.jpg",
    "factory_machine_area.jpg",
    "electrical_room.jpg",
    "chemical_storage.jpg",
    "welding_section.jpg",
    "loading_bay.jpg",
)
INCIDENT_FILES = (
    "electrical_panel_damage.jpg",
    "electrical_spark.jpg",
    "damaged_cable.jpg",
    "machine_smoke.jpg",
    "overheating_equipment.jpg",
    "chemical_spill.jpg",
    "machine_guard_missing.jpg",
    "rotating_equipment.jpg",
    "oil_spill_floor.jpg",
    "wet_floor.jpg",
)
EVIDENCE_FILES = (
    "electrical_panel_repaired.jpg",
    "cable_repaired.jpg",
    "chemical_area_cleaned.jpg",
    "loading_bay_cleaned.jpg",
    "machine_guard_fixed.jpg",
    "structural_damage.jpg",
    "blocked_walkway.jpg",
    "missing_ppe.jpg",
    "missing_gloves.jpg",
    "guardrail_shield.jpg",
    "guardrail_warning.jpg",
    "monthly_report_preview.jpg",
)
AVATARS = (
    ("avatar-kasun.svg", "KP", "#1f6f66"),
    ("avatar-arun.svg", "AK", "#c45c26"),
    ("avatar-rsilva.svg", "RS", "#3d5a80"),
    ("avatar-anonymous.svg", "AW", "#5c6570"),
    ("avatar-kamal.svg", "KA", "#8a6d1b"),
    ("avatar-nimal.svg", "NP", "#2f6f4e"),
    ("avatar-kavitha.svg", "KR", "#6b4c9a"),
)


def _avatar_svg(initials: str, color: str) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256" role="img">
  <rect width="256" height="256" fill="#121417"/>
  <circle cx="128" cy="128" r="108" fill="{color}"/>
  <text x="128" y="148" text-anchor="middle" font-family="Georgia, serif" font-size="72" fill="#f4f1ea">{initials}</text>
</svg>
"""


def _ensure_avatars() -> int:
    created = 0
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for name, initials, color in AVATARS:
        path = IMAGE_DIR / name
        if path.exists() and path.stat().st_size > 0:
            continue
        path.write_text(_avatar_svg(initials, color), encoding="utf-8")
        created += 1
    return created


def _count_existing(names: tuple[str, ...]) -> int:
    return sum(1 for name in names if (IMAGE_DIR / name).exists())


def seed() -> dict[str, int]:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_avatars()
    rejected = 0
    for path in IMAGE_DIR.iterdir():
        if not path.is_file():
            continue
        result = validate_image_file(path.name, path.read_bytes() if path.stat().st_size < 32_000_000 else b"x")
        if not result["ok"]:
            rejected += 1
    return {
        "locations": _count_existing(LOCATION_FILES),
        "incidents": _count_existing(INCIDENT_FILES),
        "evidence": _count_existing(EVIDENCE_FILES),
        "avatars": _count_existing(tuple(name for name, _, _ in AVATARS)),
        "rejected": rejected,
    }


def main() -> int:
    summary = seed()
    print("================================")
    print()
    print("Demo Image Seeder")
    print()
    print(f"Locations:\n{summary['locations']} images created")
    print()
    print(f"Incidents:\n{summary['incidents']} images created")
    print()
    print(f"Evidence:\n{summary['evidence']} images created")
    print()
    print(f"Avatars:\n{summary['avatars']} created")
    print()
    print("Complete")
    print()
    print("================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
