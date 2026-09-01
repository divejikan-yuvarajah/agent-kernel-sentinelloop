"""SentinelLoop UI consistency audit for the authenticated shell.

Run from use-cases/sentinelloop-ai:

    uv run python scripts/check_ui_consistency.py
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
HARD_SPACE = re.compile(r"(?:margin|padding|gap)\s*:\s*\d{2,}px\b")
REQUIRED_SHELL = [
    FRONTEND / "src" / "components" / "Shell" / "Shell.tsx",
    FRONTEND / "src" / "components" / "Shell" / "TopNav.tsx",
    FRONTEND / "src" / "components" / "Shell" / "MobileNav.tsx",
    FRONTEND / "src" / "components" / "Shell" / "RouterStatusPill.tsx",
    FRONTEND / "src" / "styles" / "shell.css",
]


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
    spacing_hits: list[str] = []
    missing = [str(path.relative_to(FRONTEND)) for path in REQUIRED_SHELL if not path.is_file()]

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
        if path.suffix == ".css" and "node_modules" not in path.parts:
            for match in HARD_SPACE.finditer(text):
                # Allow token definitions themselves.
                if path.name in {"tokens.css"}:
                    continue
                line_no = text.count("\n", 0, match.start()) + 1
                spacing_hits.append(f"{rel}:{line_no} {match.group(0)}")

    tokens = (FRONTEND / "design-system" / "tokens.css").read_text(encoding="utf-8")
    alias_ok = all(
        name in tokens for name in ("--space-xs", "--space-sm", "--space-md", "--space-lg", "--space-xl")
    )

    print("SentinelLoop UI Audit")
    print()
    print(f"Old colors: {len(old_hits)}")
    for item in old_hits:
        print(f"  {item}")
    print()
    print(f"Hardcoded values: {len(hardcoded)}")
    for item in hardcoded[:40]:
        print(f"  {item}")
    if len(hardcoded) > 40:
        print(f"  … {len(hardcoded) - 40} more")
    print()
    print(f"Hardcoded spacing: {len(spacing_hits)}")
    for item in spacing_hits[:20]:
        print(f"  {item}")
    print()
    print(f"Missing shell files: {len(missing)}")
    for item in missing:
        print(f"  {item}")
    print()
    print(f"Space aliases: {'OK' if alias_ok else 'MISSING'}")
    print()

    failed = bool(old_hits or hardcoded or missing or not alias_ok)
    print(f"Status: {'FAIL' if failed else 'PASS'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
