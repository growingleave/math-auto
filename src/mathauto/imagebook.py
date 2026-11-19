"""Compiles the original problem/answer photos straight into a workbook PDF.

No Vision text extraction here - this is for the common case where the
photos are already clean (printed problems, typed or neatly written
answers) and the only real job is gathering scattered files into one
ordered document, not re-reading their content. Images are placed as-is
in a flex grid (several per page sized to fit), problems first, then an
answer section.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .matcher import MatchedPair
from .sources import FileSource, SourceFile

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class ImageEntry:
    number: str
    mime_type: str
    data_b64: str


def _sort_key(group_key: str):
    return (0, int(group_key)) if group_key.isdigit() else (1, group_key)


def _to_entry(source: FileSource, file: SourceFile, number: str) -> ImageEntry:
    data = source.read_bytes(file)
    mime_type = file.mime_type or "image/jpeg"
    return ImageEntry(number=number, mime_type=mime_type, data_b64=base64.b64encode(data).decode("ascii"))


def build_entries_from_pairs(
    source: FileSource, pairs: list[MatchedPair]
) -> tuple[list[ImageEntry], list[ImageEntry]]:
    ordered = sorted(pairs, key=lambda p: _sort_key(p.group_key))
    problem_entries = [_to_entry(source, p.problem, p.group_key) for p in ordered]
    answer_entries = [_to_entry(source, p.answer, p.group_key) for p in ordered]
    return problem_entries, answer_entries


def render_html(problem_entries: list[ImageEntry], answer_entries: list[ImageEntry], title: str = "문제집") -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("imagebook.html.jinja")
    return template.render(title=title, problem_entries=problem_entries, answer_entries=answer_entries)
