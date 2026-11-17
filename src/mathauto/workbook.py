"""Turns extracted problem/answer data into the workbook HTML (problems, then an answer key)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / "templates"


@dataclass
class WorkbookEntry:
    number: str
    problem_text: str
    final_answer: str
    choices: list[str] = field(default_factory=list)
    solution_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _sort_key(number: str):
    return (0, int(number)) if number.isdigit() else (1, number)


def build_entries(items: list[tuple[str, dict, dict]]) -> list[WorkbookEntry]:
    """items: list of (group_key, problem_json, answer_json) from extractor.extract_problem/extract_answer."""
    entries = []
    for group_key, problem, answer in items:
        number = str(problem.get("problem_number") or group_key)
        notes = [n for n in (problem.get("notes"), answer.get("notes")) if n]
        entries.append(
            WorkbookEntry(
                number=number,
                problem_text=problem.get("text", ""),
                choices=problem.get("choices") or [],
                final_answer=answer.get("final_answer", ""),
                solution_steps=answer.get("solution_steps") or [],
                notes=notes,
            )
        )
    entries.sort(key=lambda e: _sort_key(e.number))
    return entries


def render_html(entries: list[WorkbookEntry], title: str = "문제집") -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("workbook.html.jinja")
    return template.render(title=title, entries=entries)
