"""Chains matching -> vision extraction -> workbook rendering -> upload into two entry points.

run_match: dry run, just reports how files would be paired (no Vision calls on
           problem/answer content, only on ambiguous-role files if enabled).
run_build: the full pipeline, ending with a PDF written via `output_source`.

Pairs the matcher couldn't confidently resolve are skipped (not guessed) and
reported back on the result, rather than silently left out or blocking the
whole run.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import extractor, workbook
from .matcher import MatchReport, match
from .pdf import render_pdf
from .sources import FileSource


@dataclass
class ExtractionFailure:
    group_key: str
    stage: str  # "problem" or "answer"
    file_name: str
    error: str


@dataclass
class BuildResult:
    match_report: MatchReport
    extraction_failures: list[ExtractionFailure] = field(default_factory=list)
    entries_built: int = 0
    output_location: Optional[str] = None


def run_match(source: FileSource, use_vision_classifier: bool = True) -> MatchReport:
    classify_fn = extractor.make_classify_role_fn(source) if use_vision_classifier else None
    files = source.list_files()
    return match(files, classify_role_fn=classify_fn)


def run_build(
    source: FileSource,
    output_source: Optional[FileSource] = None,
    title: str = "문제집",
    output_name: str = "workbook.pdf",
    use_vision_classifier: bool = True,
) -> BuildResult:
    output_source = output_source or source
    report = run_match(source, use_vision_classifier=use_vision_classifier)

    items: list[tuple[str, dict, dict]] = []
    failures: list[ExtractionFailure] = []

    for pair in report.pairs:
        try:
            problem_json = extractor.extract_problem(source.read_bytes(pair.problem), pair.problem.mime_type)
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the whole batch
            failures.append(ExtractionFailure(pair.group_key, "problem", pair.problem.name, str(e)))
            continue
        try:
            answer_json = extractor.extract_answer(source.read_bytes(pair.answer), pair.answer.mime_type)
        except Exception as e:  # noqa: BLE001
            failures.append(ExtractionFailure(pair.group_key, "answer", pair.answer.name, str(e)))
            continue
        items.append((pair.group_key, problem_json, answer_json))

    entries = workbook.build_entries(items)

    if not entries:
        return BuildResult(match_report=report, extraction_failures=failures, entries_built=0, output_location=None)

    html = workbook.render_html(entries, title=title)

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = Path(tmp_dir) / output_name
        render_pdf(html, local_path)
        output_location = output_source.upload(local_path, output_name)

    return BuildResult(
        match_report=report,
        extraction_failures=failures,
        entries_built=len(entries),
        output_location=output_location,
    )
