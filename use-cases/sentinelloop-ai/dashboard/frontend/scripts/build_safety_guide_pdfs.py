"""Build printable Safety Guide PDFs for the dashboard Knowledge Base page."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[3]
KB = ROOT / "knowledge_base"
OUT = Path(__file__).resolve().parents[1] / "public" / "guides"

MAROON = (124, 31, 46)
CHALK = (31, 17, 20)
MUTED = (122, 92, 90)
PANEL = (246, 241, 240)

GUIDES = [
    {"slug": "electrical_safety", "title": "Electrical Safety Guide", "source": KB / "electrical_safety.md"},
    {"slug": "fire_safety", "title": "Fire and Smoke Safety Guide", "source": KB / "fire_safety.md"},
    {"slug": "chemical_safety", "title": "Chemical Safety Guide", "source": KB / "chemical_safety.md"},
    {"slug": "machine_safety", "title": "Machine Safety Guide", "source": KB / "machine_safety.md"},
    {"slug": "ppe_safety", "title": "PPE Safety Guide", "source": KB / "ppe_safety.md"},
    {"slug": "general_hazards", "title": "General Workplace Hazards Guide", "source": KB / "general_hazards.md"},
]


def parse_guide(path: Path) -> tuple[list[tuple[str, list[str]]], str]:
    sections: list[tuple[str, list[str]]] = []
    current = "Rules"
    items: list[str] = []
    footer = "Always follow instructions from trained safety or emergency personnel."
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("# "):
            continue
        if line.startswith("## "):
            if items:
                sections.append((current, items))
            current = line[3:].strip()
            items = []
            continue
        if line.lower().startswith("always follow"):
            footer = line
            continue
        if line.startswith(("- ", "* ")):
            items.append(line[2:].strip())
    if items:
        sections.append((current, items))
    return sections, footer


class SafetyGuidePDF(FPDF):
    def header(self) -> None:
        self.set_fill_color(*MAROON)
        self.rect(0, 0, 210, 18, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.set_xy(16, 6)
        self.cell(0, 6, "SentinelLoop AI  |  Approved Safety Guide")
        self.set_xy(0, 18)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_text_color(*MUTED)
        self.set_font("Helvetica", "", 8)
        self.cell(
            0,
            8,
            f"Page {self.page_no()}  |  Workplace safety rules and regulations  |  Do not invent repair steps",
            align="C",
        )


def build_pdf(title: str, sections: list[tuple[str, list[str]]], footer: str, dest: Path) -> None:
    pdf = SafetyGuidePDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.add_page()
    pdf.set_y(24)
    pdf.set_text_color(*CHALK)
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_x(16)
    pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.set_x(16)
    pdf.multi_cell(
        178,
        5,
        "Approved worker rules and site regulations from the SentinelLoop knowledge base. "
        "These instructions support factory safety practice. They do not replace trained "
        "emergency responders or a competent person's isolation and repair work.",
    )
    pdf.ln(4)

    for heading, lines in sections:
        pdf.set_text_color(*MAROON)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_x(16)
        pdf.cell(0, 8, heading, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*MAROON)
        pdf.set_line_width(0.5)
        y = pdf.get_y()
        pdf.line(16, y, 194, y)
        pdf.ln(3)
        pdf.set_text_color(*CHALK)
        pdf.set_font("Helvetica", "", 11)
        for index, line in enumerate(lines, start=1):
            pdf.set_x(16)
            pdf.multi_cell(178, 6.2, f"{index}.  {line}")
            pdf.ln(0.6)
        pdf.ln(3)

    pdf.set_fill_color(*PANEL)
    pdf.set_text_color(*MAROON)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_x(16)
    pdf.multi_cell(178, 7, footer, fill=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(dest))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for guide in GUIDES:
        sections, footer = parse_guide(Path(guide["source"]))
        dest = OUT / f"{guide['slug']}.pdf"
        build_pdf(str(guide["title"]), sections, footer, dest)
        print(f"wrote {dest} sections={len(sections)} rules={sum(len(s[1]) for s in sections)}")


if __name__ == "__main__":
    main()
