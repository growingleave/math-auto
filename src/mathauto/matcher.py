"""Pairs problem files with their answer files without assuming a fixed naming convention.

We don't control how the source Drive folder is organized (it was handed to
us by someone else), so this tries several conventions in order and reports
anything it can't confidently resolve instead of guessing silently:

  1. folder_split      - two sibling folders, e.g. "문제"/"정답" or "problems"/"answers"
  2. filename_marker    - one folder, filenames carry a role marker: "01_문제.jpg"/
                          "01_정답.jpg", "ch3_question.png"/"ch3_answer.png", "q1.jpg"/"a1.jpg"
  3. numeric_sequence    - no marker at all, just numbered files; role is resolved
                          by an optional vision classifier callback, otherwise
                          flagged for manual review

Everything that doesn't land in a confident pair ends up in `unmatched` or
`ambiguous` on the returned MatchReport, so a human can look at the report
before anything gets sent to the (costly) extraction step.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional

from .sources import SourceFile

Role = Literal["problem", "answer"]

PROBLEM_WORDS = {"문제", "질문", "problem", "problems", "question", "questions", "prob", "ques"}
ANSWER_WORDS = {"정답", "답안", "해설", "풀이", "답", "answer", "answers", "solution", "solutions", "ans", "sol"}
PROBLEM_LETTERS = {"q", "p"}
ANSWER_LETTERS = {"a", "s"}

_TOKEN_SPLIT_RE = re.compile(r"[^0-9a-zA-Z가-힣]+")
_NUMBER_RE = re.compile(r"\d+")
_GLUED_LETTER_NUM_RE = re.compile(r"^([qpas])[\s_\-]*([0-9]+)$")
_GLUED_NUM_LETTER_RE = re.compile(r"^([0-9]+)[\s_\-]*([qpas])$")


def _role_for_letter(letter: str) -> Role:
    return "problem" if letter in PROBLEM_LETTERS else "answer"


def extract_number(text: str) -> Optional[str]:
    m = _NUMBER_RE.search(text)
    return m.group() if m else None


def detect_role(stem: str) -> tuple[Optional[Role], Optional[str], Optional[str]]:
    """Returns (role, base_key, number) detected from a filename stem (no extension)."""
    low = stem.strip().lower()

    m = _GLUED_LETTER_NUM_RE.fullmatch(low)
    if m:
        letter, num = m.groups()
        return _role_for_letter(letter), num, num

    m = _GLUED_NUM_LETTER_RE.fullmatch(low)
    if m:
        num, letter = m.groups()
        return _role_for_letter(letter), num, num

    tokens = [t for t in _TOKEN_SPLIT_RE.split(low) if t]

    matched_token = None
    role: Optional[Role] = None
    for tok in tokens:
        if tok in PROBLEM_WORDS or tok in ANSWER_WORDS:
            role = "problem" if tok in PROBLEM_WORDS else "answer"
            matched_token = tok
            break
    if role is None:
        for tok in tokens:
            if tok in PROBLEM_LETTERS or tok in ANSWER_LETTERS:
                role = _role_for_letter(tok)
                matched_token = tok
                break
    if role is None:
        return None, None, None

    remaining = [t for t in tokens if t != matched_token]
    base_key = "_".join(remaining) if remaining else None
    return role, base_key, extract_number(low)


@dataclass
class MatchedPair:
    problem: SourceFile
    answer: SourceFile
    group_key: str
    strategy: str
    confidence: float


@dataclass
class MatchReport:
    pairs: list[MatchedPair] = field(default_factory=list)
    unmatched: list[SourceFile] = field(default_factory=list)
    ambiguous: list[list[SourceFile]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pairs": [
                {
                    "group_key": p.group_key,
                    "strategy": p.strategy,
                    "confidence": p.confidence,
                    "problem": p.problem.name,
                    "answer": p.answer.name,
                }
                for p in self.pairs
            ],
            "unmatched": [f.name for f in self.unmatched],
            "ambiguous": [[f.name for f in group] for group in self.ambiguous],
        }

    def to_markdown(self) -> str:
        lines = ["# 매칭 결과", "", f"확정된 쌍: {len(self.pairs)}개", ""]
        for p in sorted(self.pairs, key=lambda p: p.group_key):
            lines.append(f"- [{p.strategy}, 확신도 {p.confidence:.2f}] {p.problem.name}  <->  {p.answer.name}")
        if self.ambiguous:
            lines += ["", f"## 확인 필요 (모호함): {len(self.ambiguous)}건"]
            for group in self.ambiguous:
                lines.append("- " + ", ".join(f.name for f in group))
        if self.unmatched:
            lines += ["", f"## 짝을 찾지 못한 파일: {len(self.unmatched)}개"]
            for f in self.unmatched:
                lines.append(f"- {f.name}")
        return "\n".join(lines)


def _group_by_parent(files: list[SourceFile]) -> dict[str, list[SourceFile]]:
    groups: dict[str, list[SourceFile]] = defaultdict(list)
    for f in files:
        if f.parent_name:
            groups[f.parent_name].append(f)
    return groups


def _match_folder_split(files: list[SourceFile]) -> tuple[list[MatchedPair], list[SourceFile], list[SourceFile]]:
    pairs: list[MatchedPair] = []
    consumed_ids: set[str] = set()
    consumed_parents: set[str] = set()

    by_parent = _group_by_parent(files)
    parent_roles: dict[str, Role] = {}
    for pname in by_parent:
        role, _, _ = detect_role(pname)
        if role:
            parent_roles[pname] = role

    problem_parents = [p for p, r in parent_roles.items() if r == "problem"]
    answer_parents = [p for p, r in parent_roles.items() if r == "answer"]

    if len(problem_parents) == 1 and len(answer_parents) == 1:
        p_parent, a_parent = problem_parents[0], answer_parents[0]
        p_files, a_files = by_parent[p_parent], by_parent[a_parent]

        p_by_num = {extract_number(Path(f.name).stem): f for f in p_files if extract_number(Path(f.name).stem)}
        a_by_num = {extract_number(Path(f.name).stem): f for f in a_files if extract_number(Path(f.name).stem)}
        common_nums = sorted(set(p_by_num) & set(a_by_num), key=int)

        for n in common_nums:
            pf, af = p_by_num[n], a_by_num[n]
            pairs.append(MatchedPair(pf, af, group_key=n, strategy="folder_split+number", confidence=0.95))
            consumed_ids.update([pf.id, af.id])

        rem_p = [f for f in p_files if f.id not in consumed_ids]
        rem_a = [f for f in a_files if f.id not in consumed_ids]
        if rem_p and rem_a and not common_nums:
            for pf, af in zip(sorted(rem_p, key=lambda f: f.name), sorted(rem_a, key=lambda f: f.name)):
                pairs.append(MatchedPair(pf, af, group_key=pf.name, strategy="folder_split+order", confidence=0.6))
                consumed_ids.update([pf.id, af.id])
            rem_p = [f for f in rem_p if f.id not in consumed_ids]
            rem_a = [f for f in rem_a if f.id not in consumed_ids]

        consumed_parents.update([p_parent, a_parent])
        leftover_unmatched = rem_p + rem_a
    else:
        leftover_unmatched = []

    remaining = [f for f in files if f.parent_name not in consumed_parents]
    return pairs, leftover_unmatched, remaining


def _match_filename_marker(
    files: list[SourceFile],
) -> tuple[list[MatchedPair], list[SourceFile], list[list[SourceFile]], list[SourceFile]]:
    groups: dict[str, list[tuple[SourceFile, Role]]] = defaultdict(list)
    no_role: list[SourceFile] = []

    for f in files:
        stem = Path(f.name).stem
        role, base_key, number = detect_role(stem)
        if role is None:
            no_role.append(f)
            continue
        key = base_key or number or stem
        groups[key].append((f, role))

    pairs: list[MatchedPair] = []
    ambiguous: list[list[SourceFile]] = []
    unmatched: list[SourceFile] = []

    for key, items in groups.items():
        if len(items) == 2:
            (f1, r1), (f2, r2) = items
            if r1 != r2:
                problem_f, answer_f = (f1, f2) if r1 == "problem" else (f2, f1)
                pairs.append(MatchedPair(problem_f, answer_f, group_key=key, strategy="filename_marker", confidence=0.9))
            else:
                ambiguous.append([f1, f2])
        elif len(items) == 1:
            unmatched.append(items[0][0])
        else:
            ambiguous.append([it[0] for it in items])

    return pairs, unmatched, ambiguous, no_role


def _match_numeric_sequence(
    files: list[SourceFile], classify_role_fn: Optional[Callable[[SourceFile], Role]]
) -> tuple[list[MatchedPair], list[SourceFile], list[list[SourceFile]]]:
    num_groups: dict[str, list[SourceFile]] = defaultdict(list)
    no_number: list[SourceFile] = []

    for f in files:
        n = extract_number(Path(f.name).stem)
        if n is None:
            no_number.append(f)
        else:
            num_groups[n].append(f)

    pairs: list[MatchedPair] = []
    ambiguous: list[list[SourceFile]] = []
    unmatched: list[SourceFile] = list(no_number)

    for n, items in num_groups.items():
        if len(items) == 1:
            unmatched.append(items[0])
            continue
        if len(items) != 2:
            ambiguous.append(items)
            continue
        if classify_role_fn is None:
            ambiguous.append(items)
            continue
        f1, f2 = items
        r1, r2 = classify_role_fn(f1), classify_role_fn(f2)
        if r1 != r2 and r1 in ("problem", "answer") and r2 in ("problem", "answer"):
            problem_f, answer_f = (f1, f2) if r1 == "problem" else (f2, f1)
            pairs.append(MatchedPair(problem_f, answer_f, group_key=n, strategy="numeric_sequence+vision", confidence=0.6))
        else:
            ambiguous.append(items)

    return pairs, unmatched, ambiguous


def match(files: list[SourceFile], classify_role_fn: Optional[Callable[[SourceFile], Role]] = None) -> MatchReport:
    pairs: list[MatchedPair] = []
    ambiguous: list[list[SourceFile]] = []
    unmatched: list[SourceFile] = []

    folder_pairs, folder_leftover_unmatched, remaining = _match_folder_split(files)
    pairs += folder_pairs
    unmatched += folder_leftover_unmatched

    marker_pairs, marker_unmatched, marker_ambiguous, no_role = _match_filename_marker(remaining)
    pairs += marker_pairs
    unmatched += marker_unmatched
    ambiguous += marker_ambiguous

    numeric_pairs, numeric_unmatched, numeric_ambiguous = _match_numeric_sequence(no_role, classify_role_fn)
    pairs += numeric_pairs
    unmatched += numeric_unmatched
    ambiguous += numeric_ambiguous

    pairs.sort(key=lambda p: (0, int(p.group_key)) if p.group_key.isdigit() else (1, p.group_key))
    return MatchReport(pairs=pairs, unmatched=unmatched, ambiguous=ambiguous)
