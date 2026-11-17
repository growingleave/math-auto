"""Reads problem/answer images with Claude's vision and returns structured data.

Requires ANTHROPIC_API_KEY in the environment. Model is configurable via
the MATHAUTO_MODEL env var since vision model availability changes faster
than this code does.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Callable

from .sources import FileSource, SourceFile

DEFAULT_MODEL = os.environ.get("MATHAUTO_MODEL", "claude-sonnet-5-5")

PROBLEM_PROMPT = """\
이 이미지는 수학 문제 사진입니다. 다음 JSON 형식으로만 답하세요 (다른 텍스트 없이):
{
  "problem_number": "사진에 적힌 문제 번호(없으면 null)",
  "text": "문제 지문 전체. 수식은 LaTeX로 $...$ 안에 표기",
  "choices": ["선택지가 있으면 배열로, 없으면 null"],
  "has_diagram": true 또는 false,
  "notes": "읽기 어렵거나 불확실한 부분 설명 (없으면 null)"
}"""

ANSWER_PROMPT = """\
이 이미지는 (손글씨일 수 있는) 수학 문제의 정답/풀이 사진입니다. 다음 JSON 형식으로만 답하세요 (다른 텍스트 없이):
{
  "final_answer": "최종 정답. 수식은 LaTeX로 $...$ 안에 표기",
  "solution_steps": ["풀이 과정을 단계별로 나눈 배열 (없으면 빈 배열)"],
  "notes": "읽기 어렵거나 불확실한 부분 설명 (없으면 null)"
}"""

ROLE_PROMPT = (
    "이 이미지는 수학 '문제' 사진이거나 '정답/풀이' 사진입니다. "
    "둘 중 하나만, 정확히 한 단어로 답하세요: PROBLEM 또는 ANSWER."
)


def _client():
    from anthropic import Anthropic

    return Anthropic()


def _image_block(image_bytes: bytes, mime_type: str) -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime_type, "data": base64.b64encode(image_bytes).decode("ascii")},
    }


def _text_of(response) -> str:
    return "".join(block.text for block in response.content if block.type == "text")


def _parse_json_response(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def _extract(image_bytes: bytes, mime_type: str, prompt: str) -> dict:
    response = _client().messages.create(
        model=DEFAULT_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": [_image_block(image_bytes, mime_type), {"type": "text", "text": prompt}]}],
    )
    return _parse_json_response(_text_of(response))


def extract_problem(image_bytes: bytes, mime_type: str) -> dict:
    return _extract(image_bytes, mime_type, PROBLEM_PROMPT)


def extract_answer(image_bytes: bytes, mime_type: str) -> dict:
    return _extract(image_bytes, mime_type, ANSWER_PROMPT)


def classify_role(image_bytes: bytes, mime_type: str) -> str:
    response = _client().messages.create(
        model=DEFAULT_MODEL,
        max_tokens=10,
        messages=[{"role": "user", "content": [_image_block(image_bytes, mime_type), {"type": "text", "text": ROLE_PROMPT}]}],
    )
    raw = _text_of(response).strip().upper()
    if "PROBLEM" in raw:
        return "problem"
    if "ANSWER" in raw:
        return "answer"
    raise ValueError(f"모델 응답에서 역할을 판단할 수 없음: {raw!r}")


def make_classify_role_fn(source: FileSource) -> Callable[[SourceFile], str]:
    """Adapts classify_role to the (file) -> role shape matcher.match expects."""

    def _fn(file: SourceFile) -> str:
        return classify_role(source.read_bytes(file), file.mime_type)

    return _fn
