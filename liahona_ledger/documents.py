"""Fills the ward's actual Word templates with meeting data and produces
the three weekly deliverables: the bishopric agenda (.docx), the printable
program (.docx -> .pdf), and the announcements email (.md / plain text).

Placeholder style matches the templates as supplied: single square-bracket
tokens like [PRESIDING], [OPENING_HYMN_PAGE], etc. A handful of tokens
(agenda: [SPEAKER] x2; program: [SPECIAL MUSIC] on a merged cell) repeat
literally in the document -- those are resolved in document order rather
than all-at-once, so the first occurrence gets the first value and so on.

Two small gaps in the source templates were patched (see README "Template
notes") because the underlying content had no token to fill at all:
  - Bishop's Business (agenda): was a bare heading -> added [BISHOPS_BUSINESS]
  - Hymn cells (program): were static "#"" scaffolding -> added
    #[..._PAGE] "[..._TITLE]" tokens
  - Ward Announcements (program): had one week's leftover sample copy ->
    replaced with [ANNOUNCEMENTS_BLOCK]
Everything else is exactly as provided.
"""
from __future__ import annotations

import copy
import datetime as dt
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from docx import Document
from docx.table import Table

from .models import Meeting, Speaker, WardBusinessItem

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

AGENDA_TEMPLATES = {
    "sacrament": TEMPLATES_DIR / "agenda_sacrament_template.docx",
    "fast_and_testimony": TEMPLATES_DIR / "agenda_fast_and_testimony_template.docx",
}
PROGRAM_TEMPLATES = {
    "sacrament": TEMPLATES_DIR / "program_sacrament_template.docx",
    "fast_and_testimony": TEMPLATES_DIR / "program_fast_and_testimony_template.docx",
}

BISHOPS_BUSINESS_CATEGORIES = {
    "baby_blessing": "Baby Blessing",
    "confirmation": "Confirmation",
    "baptism": "Baptism",
    "other": "Ward Business",
}

# Ward-business table headers as they appear (minus the blank numbering
# column) -> category.
WARD_BUSINESS_TABLES = {
    ("Name",): "move_in",
    ("Name", "Released as:"): "release",
    ("Name", "Called/Sustained as:", "Set-Apart (\u2714)"): "calling_sustaining",
}


def _template_key(meeting_type: str) -> str:
    return "fast_and_testimony" if meeting_type == "fast_and_testimony" else "sacrament"


def _hymn_map(meeting: Meeting) -> dict[str, str]:
    return {
        "OPENING_HYMN_PAGE": meeting.opening_hymn_number or "",
        "OPENING_HYMN_TITLE": meeting.opening_hymn_title or "",
        "SACRAMENT_PAGE": meeting.sacrament_hymn_number or "",
        "SACRAMENT_TITLE": meeting.sacrament_hymn_title or "",
        "CLOSING_PAGE": meeting.closing_hymn_number or "",
        "CLOSING_TITLE": meeting.closing_hymn_title or "",
    }


def _speaker_display(s: Speaker) -> str:
    return f"{s.name} \u2014 {s.topic}" if s.topic else s.name


def _musical_numbers_display(meeting: Meeting) -> str:
    lines = []
    for mn in meeting.musical_numbers:
        title = f", \u201c{mn.title}\u201d" if mn.title else ""
        lines.append(f"{mn.performer}{title}")
    return "\n".join(lines)


def _bishops_business_block(meeting: Meeting) -> str:
    lines = []
    for wb in meeting.ward_business:
        label = BISHOPS_BUSINESS_CATEGORIES.get(wb.category)
        if not label:
            continue
        desc = f" \u2014 {wb.description}" if wb.description else ""
        lines.append(f"{label}: {wb.person_name}{desc}")
    return "\n".join(lines)


def _announcements_block(meeting: Meeting, channel: str) -> str:
    field = {"agenda": "include_in_agenda", "program": "include_in_program",
             "email": "include_in_email"}[channel]
    items = [a for a in meeting.announcements if getattr(a, field)]
    if not items:
        return "(none this week)"
    return "\n".join(f"\u2022 {a.text}" for a in items)


def build_agenda_map(meeting: Meeting, ward_name: str = "") -> tuple[dict[str, str], dict[str, list[str]]]:
    """Returns (simple_map, sequential_map) for the agenda template."""
    date = dt.date.fromisoformat(meeting.meeting_date)
    non_youth = [s for s in meeting.speakers if not s.is_youth]
    youth = next((s for s in meeting.speakers if s.is_youth), None)

    simple = {
        "WARD_NAME": ward_name,
        "MEETING_DATE": date.strftime("%B %-d, %Y"),
        "CONDUCTING": meeting.conducting or "",
        "PRESIDING": meeting.presiding or "",
        "Chorister": meeting.chorister or "",
        "Organist": meeting.organist or "",
        "PIANIST": meeting.pianist or "",
        "ANNOUNCEMENTS": _announcements_block(meeting, "agenda"),
        "YOUTH_SPEAKER": _speaker_display(youth) if youth else "(none scheduled)",
        "SPECIAL_MUSICAL_NUMBER": _musical_numbers_display(meeting),
        "BISHOPS_BUSINESS": _bishops_business_block(meeting),
        **_hymn_map(meeting),
    }
    sequential = {
        "SPEAKER": [_speaker_display(s) for s in non_youth] or ["(TBD)"],
    }
    return simple, sequential


def build_program_map(meeting: Meeting, ward_name: str = "") -> dict[str, str]:
    """Returns the simple_map for the program template (no repeated tokens)."""
    date = dt.date.fromisoformat(meeting.meeting_date)
    non_youth = [s for s in meeting.speakers if not s.is_youth]
    youth = next((s for s in meeting.speakers if s.is_youth), None)
    speaker1 = non_youth[0] if len(non_youth) > 0 else None
    speaker2 = non_youth[1] if len(non_youth) > 1 else None

    return {
        "DATE": date.strftime("%B %-d, %Y"),
        "COVER_IMAGE": "",  # manual step -- see README "Template notes"
        "SPIRITUAl_THOUGHT": meeting.spiritual_thought or "",
        "AUTHOR": meeting.spiritual_thought_author or "",
        "PRESIDING": meeting.presiding or "",
        "CONDUCTING": meeting.conducting or "",
        "CHORISTER": meeting.chorister or "",
        "ORGANIST": meeting.organist or "",
        "PIANIST": meeting.pianist or "",
        "YOUTH SPEAKER": _speaker_display(youth) if youth else "(none scheduled)",
        "SPEAKER1": _speaker_display(speaker1) if speaker1 else "(TBD)",
        "SPEAKER2": _speaker_display(speaker2) if speaker2 else "(TBD)",
        "SPECIAL MUSIC": _musical_numbers_display(meeting),
        "ANNOUNCEMENTS_BLOCK": _announcements_block(meeting, "program"),
        **_hymn_map(meeting),
    }


# ---------------------------------------------------------------------- #
# Bracket-token replacement engine
# ---------------------------------------------------------------------- #
def _set_run_text_multiline(run, text: str) -> None:
    """Set a run's text, turning '\\n' into a real line break (<w:br/>)
    within that SAME run, preserving whatever formatting (bold, size, etc.)
    the run already had."""
    lines = text.split("\n")
    run.text = lines[0]
    for line in lines[1:]:
        run.add_break()
        run.add_text(line)


class _BracketFiller:
    """Replaces [TOKEN] placeholders across a document. Tokens in
    `sequential` are consumed left-to-right, occurrence by occurrence
    (for the templates' handful of literally-repeated placeholders);
    everything else is a plain one-value-everywhere substitution."""

    def __init__(self, simple: dict[str, str], sequential: Optional[dict[str, list[str]]] = None):
        self.simple = simple
        self.sequential = sequential or {}
        self._seq_index = {k: 0 for k in self.sequential}

    def _next_sequential(self, key: str) -> str:
        i = self._seq_index[key]
        values = self.sequential[key]
        self._seq_index[key] = i + 1
        return values[i] if i < len(values) else ""

    def _resolve(self, text: str) -> str:
        for key in self.sequential:
            token = f"[{key}]"
            while token in text:
                text = text.replace(token, self._next_sequential(key), 1)
        for key, value in self.simple.items():
            text = text.replace(f"[{key}]", value)
        return text

    def fill_paragraph(self, paragraph) -> None:
        full_text = "".join(r.text for r in paragraph.runs)
        if "[" not in full_text:
            return
        unresolved = False
        for run in paragraph.runs:
            if "[" not in run.text:
                continue
            new_text = self._resolve(run.text)
            if "[" in new_text:
                unresolved = True
            if new_text != run.text:
                _set_run_text_multiline(run, new_text)
        if not unresolved:
            return
        # Fallback for a token split across multiple runs by Word: rebuild
        # using the first run's formatting.
        full_text = "".join(r.text for r in paragraph.runs)
        new_text = self._resolve(full_text)
        if new_text == full_text or not paragraph.runs:
            return
        template_run = paragraph.runs[0]
        for run in paragraph.runs[1:]:
            run.text = ""
        _set_run_text_multiline(template_run, new_text)

    def fill_document(self, doc: Document) -> None:
        for paragraph in doc.paragraphs:
            self.fill_paragraph(paragraph)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self.fill_paragraph(paragraph)
        for section in doc.sections:
            for container in (section.header, section.footer):
                for paragraph in container.paragraphs:
                    self.fill_paragraph(paragraph)


# ---------------------------------------------------------------------- #
# Ward-business dynamic tables (Move-Ins / Releases / Calling & Sustaining)
# ---------------------------------------------------------------------- #
def _set_cell_text(cell, text: str) -> None:
    para = cell.paragraphs[0]
    if para.runs:
        run = para.runs[0]
        run.text = text
        for extra in para.runs[1:]:
            extra.text = ""
    else:
        para.add_run(text)
    for extra_p in cell.paragraphs[1:]:
        extra_p._p.getparent().remove(extra_p._p)


def _header_key(table: Table) -> Optional[tuple[str, ...]]:
    if not table.rows:
        return None
    key = tuple(c.text.strip() for c in table.rows[0].cells[1:])
    return key if key in WARD_BUSINESS_TABLES else None


def _rows_for_category(items: list[WardBusinessItem], category: str) -> list[list[str]]:
    matches = [i for i in items if i.category == category]
    if category == "move_in":
        return [[i.person_name] for i in matches]
    if category == "release":
        return [[i.person_name, i.description or ""] for i in matches]
    if category == "calling_sustaining":
        return [[i.person_name, i.description or "", "\u2714" if i.set_apart else ""] for i in matches]
    return []


def _fill_ward_business_table(table: Table, rows_data: list[list[str]]) -> None:
    if not rows_data:
        return  # leave the template's default blank numbered rows untouched
    while len(table.rows) - 1 < len(rows_data):
        new_tr = copy.deepcopy(table.rows[-1]._tr)
        table._tbl.append(new_tr)
    while len(table.rows) - 1 > len(rows_data):
        last_row = table.rows[-1]
        last_row._tr.getparent().remove(last_row._tr)
    for i, values in enumerate(rows_data):
        row = table.rows[i + 1]
        _set_cell_text(row.cells[0], str(i + 1))
        for col_idx, value in enumerate(values, start=1):
            _set_cell_text(row.cells[col_idx], value)


def _fill_ward_business_tables(doc: Document, ward_business: list[WardBusinessItem]) -> None:
    for table in doc.tables:
        key = _header_key(table)
        if key is None:
            continue
        category = WARD_BUSINESS_TABLES[key]
        _fill_ward_business_table(table, _rows_for_category(ward_business, category))


# ---------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------- #
def convert_to_pdf(docx_path: Path, output_dir: Optional[Path] = None) -> Path:
    """Convert a .docx to .pdf using LibreOffice headless (must be installed
    and on PATH). Raises RuntimeError with guidance if it's missing."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError(
            "LibreOffice was not found on this machine (needed to convert "
            ".docx to .pdf). Install it from https://www.libreoffice.org/ "
            "and make sure `soffice` is on your PATH, then try again. "
            "The .docx was still generated successfully."
        )
    output_dir = output_dir or docx_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(docx_path)],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed:\n{result.stdout}\n{result.stderr}")
    return output_dir / (docx_path.stem + ".pdf")


def generate_agenda(meeting: Meeting, output_path: Path, template_path: Optional[Path] = None,
                     ward_name: str = "") -> Path:
    template = template_path or AGENDA_TEMPLATES[_template_key(meeting.meeting_type)]
    doc = Document(str(template))
    simple, sequential = build_agenda_map(meeting, ward_name)
    _BracketFiller(simple, sequential).fill_document(doc)
    _fill_ward_business_tables(doc, meeting.ward_business)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def generate_program(meeting: Meeting, output_path: Path, template_path: Optional[Path] = None,
                      ward_name: str = "", as_pdf: bool = True) -> Path:
    template = template_path or PROGRAM_TEMPLATES[_template_key(meeting.meeting_type)]
    doc = Document(str(template))
    simple = build_program_map(meeting, ward_name)
    _BracketFiller(simple).fill_document(doc)
    docx_path = output_path.with_suffix(".docx")
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    if as_pdf:
        return convert_to_pdf(docx_path, output_dir=output_path.parent)
    return docx_path


def generate_announcements_email(meeting: Meeting, output_path: Path, ward_name: str = "") -> Path:
    date = dt.date.fromisoformat(meeting.meeting_date)
    heading = f"Announcements for {date.strftime('%B %-d, %Y')}"
    items = [a for a in meeting.announcements if a.include_in_email]
    lines = [f"# {heading}", ""]
    if ward_name:
        lines.insert(0, ward_name)
    if not items:
        lines.append("(No announcements this week.)")
    else:
        for a in items:
            lines.append(f"- {a.text}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
