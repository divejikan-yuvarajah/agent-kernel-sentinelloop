"""Generate WhatsApp location QR codes from locations.yaml.

Does not mutate incidents or call agents. Output is print-ready PNGs plus
``location_registry.json`` for dashboard analytics.

Usage (from use-cases/sentinelloop-ai):

    uv run python scripts/generate_location_qr.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.location_catalog import LocationConfigError, LocationEntry, load_locations  # noqa: E402
from tools.qr_tags import format_loc_prefix  # noqa: E402

INK = "#1C2024"
CHALK = "#F2F0EA"
MUTED = "#B7B5AE"

A4_PX = (1240, 1754)  # 150 dpi
STICKER_PX = (720, 900)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _whatsapp_number() -> str:
    raw = os.environ.get("WHATSAPP_QR_NUMBER") or os.environ.get("WHATSAPP_DISPLAY_NUMBER") or ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 8:
        raise LocationConfigError(
            "WHATSAPP_QR_NUMBER is required (E.164 digits, no plus). Set it in .env before generating QR codes."
        )
    if len(digits) > 16:
        raise LocationConfigError("WHATSAPP_QR_NUMBER is too long")
    return digits


def deep_link(number: str, encoded_message: str) -> str:
    return f"https://wa.me/{number}?text={quote(encoded_message)}"


def _font(size: int):
    from PIL import ImageFont

    for name in ("arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _qr_image(payload: str, *, box_size: int = 12):
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=box_size,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color=INK, back_color=CHALK).convert("RGB")


def _center(draw, text: str, y: int, font, fill: str, width: int) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (width - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _compose_frame(
    entry: LocationEntry,
    qr_img,
    size: tuple[int, int],
    *,
    subtitle: str,
) -> Any:
    from PIL import Image, ImageDraw

    width, height = size
    canvas = Image.new("RGB", size, CHALK)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((40, 40, width - 40, height - 40), outline=INK, width=3)

    brand = _font(42 if size[0] > 1000 else 32)
    label = _font(22 if size[0] > 1000 else 16)
    value = _font(28 if size[0] > 1000 else 20)
    small = _font(16 if size[0] > 1000 else 12)

    _center(draw, "SENTINELLOOP", 72, brand, INK, width)
    _center(draw, subtitle, 130, small, MUTED, width)

    qr_w = min(qr_img.width, width - 200)
    if qr_img.width != qr_w:
        qr_img = qr_img.resize((qr_w, qr_w))
    qr_x = (width - qr_img.width) // 2
    qr_y = 190 if size[0] > 1000 else 160
    canvas.paste(qr_img, (qr_x, qr_y))

    y = qr_y + qr_img.height + 48
    _center(draw, "LOCATION", y, label, MUTED, width)
    _center(draw, entry.location, y + 32, value, INK, width)
    _center(draw, "EQUIPMENT", y + 84, label, MUTED, width)
    equipment = entry.equipment if entry.version == 1 else f"{entry.equipment} v{entry.version}"
    _center(draw, equipment, y + 116, value, INK, width)
    _center(draw, entry.qr_id or "", height - 90, small, MUTED, width)
    return canvas


def generate_location_qrs(
    *,
    config_path: Path,
    output_dir: Path,
    whatsapp_number: str | None = None,
) -> dict[str, Any]:
    entries = load_locations(config_path)
    number = whatsapp_number or _whatsapp_number()
    stickers = output_dir
    posters = output_dir / "posters"
    stickers.mkdir(parents=True, exist_ok=True)
    posters.mkdir(parents=True, exist_ok=True)

    generated_at = _now()
    registry: list[dict[str, Any]] = []
    names: list[str] = []
    for entry in entries:
        assert entry.qr_id is not None
        encoded = format_loc_prefix(entry.location, entry.equipment)
        url = deep_link(number, encoded)
        qr_hi = _qr_image(url, box_size=14)
        sticker = _compose_frame(entry, qr_hi, STICKER_PX, subtitle="Scan to report a workplace hazard")
        poster = _compose_frame(
            entry,
            _qr_image(url, box_size=18),
            A4_PX,
            subtitle="Camera or WhatsApp scan  ·  then describe the hazard  ·  location is already filled",
        )
        sticker_name = f"{entry.qr_id}.png"
        poster_name = f"{entry.qr_id}-poster.png"
        sticker_path = stickers / sticker_name
        poster_path = posters / poster_name
        sticker.save(sticker_path, "PNG")
        poster.save(poster_path, "PNG")
        registry.append(
            {
                "qr_id": entry.qr_id,
                "location": entry.location,
                "equipment": entry.equipment,
                "area_code": entry.area_code,
                "building": entry.building,
                "floor": entry.floor,
                "department": entry.department,
                "safety_zone": entry.safety_zone,
                "version": entry.version,
                "created": generated_at,
                "encoded_message": encoded,
                "qr_file_path": sticker_path.as_posix(),
                "poster_file_path": poster_path.as_posix(),
                "scans": 0,
                "reports_created": 0,
            }
        )
        names.append(f"{entry.location} - {entry.equipment}")

    # Store paths relative to the use-case root when possible.
    root = config_path.parent
    for row in registry:
        for key in ("qr_file_path", "poster_file_path"):
            path = Path(row[key])
            try:
                row[key] = path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                row[key] = path.as_posix()

    registry_path = stickers / "location_registry.json"
    payload = json.dumps({"generated_at": generated_at, "items": registry}, indent=2) + "\n"
    registry_path.write_text(payload, encoding="utf-8")
    return {
        "count": len(entries),
        "names": names,
        "registry_path": registry_path,
        "items": registry,
    }


def _print_summary(result: dict[str, Any]) -> None:
    print("Generated QR Codes:\n")
    for name in result["names"]:
        print(f"✓ {name}")
    print(f"\nTotal:\n{result['count']} QR codes generated")
    print(f"Registry: {result['registry_path']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate SentinelLoop location QR posters.")
    parser.add_argument("--config", type=Path, default=ROOT / "locations.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "assets" / "qr")
    parser.add_argument("--whatsapp-number", default=None, help="Override WHATSAPP_QR_NUMBER (digits only).")
    args = parser.parse_args(argv)
    try:
        result = generate_location_qrs(
            config_path=args.config,
            output_dir=args.output,
            whatsapp_number=args.whatsapp_number,
        )
    except LocationConfigError as exc:
        print(f"QR generation failed: {exc}", file=sys.stderr)
        return 1
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
