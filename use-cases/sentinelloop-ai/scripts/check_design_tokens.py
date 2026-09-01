"""Scan the dashboard frontend for leftover graphite colors and hardcoded hex.

Run from use-cases/sentinelloop-ai:

    uv run python scripts/check_design_tokens.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "dashboard" / "frontend"

OLD_COLORS = {
    "#1c2024",
    "#262b31",
    "#e8a33d",
    "#ff2a2a",
    "#d64545",
    "#f2f0ea",
    "#0b1220",
    "#f3f6fb",
    "#2e343c",
    "#3a4047",
    "#4d555e",
    "#b7b5ae",
}

ALLOWED_HEX_FILES = {
    FRONTEND / "design-system" / "tokens.css",
    FRONTEND / "design-system" / "tokens.ts",
    FRONTEND / "design-system" / "colors.ts",
    FRONTEND / "index.html",
}

SKIP_DIRS = {"node_modules", "dist", ".vite"}
SCAN_SUFFIXES = {".css", ".ts", ".tsx", ".html"}
HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in FRONTEND.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return files


def main() -> int:
    old_hits: list[str] = []
    hardcoded: list[str] = []

    for path in iter_files():
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(FRONTEND).as_posix()
        for match in HEX.finditer(text):
            value = match.group(0).lower()
            if len(value) == 4:
                value = "#" + "".join(ch * 2 for ch in value[1:])
            line_no = text.count("\n", 0, match.start()) + 1
            loc = f"{rel}:{line_no} {match.group(0)}"
            if value in OLD_COLORS:
                old_hits.append(loc)
            if path not in ALLOWED_HEX_FILES:
                hardcoded.append(loc)

    print("Design Token Audit")
    print()
    print(f"Old Colors Found: {len(old_hits)}")
    for item in old_hits:
        print(f"  {item}")
    print()
    print(f"Hardcoded Colors: {len(hardcoded)}")
    for item in hardcoded:
        print(f"  {item}")
    print()
    if old_hits:
        print("Review Required")
        return 1
    if hardcoded:
        print("Review Required")
        return 1
    print("Pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
