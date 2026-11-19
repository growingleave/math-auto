import base64
from pathlib import Path
from unittest.mock import patch

from mathauto import pipeline
from mathauto.sources import LocalFolderSource

TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_run_build_end_to_end(tmp_path):
    (tmp_path / "01_문제.jpg").write_bytes(b"fake-problem-image-bytes")
    (tmp_path / "01_정답.jpg").write_bytes(b"fake-answer-image-bytes")

    source = LocalFolderSource(tmp_path)
    output_source = LocalFolderSource(tmp_path, output_dir=tmp_path / "out")

    fake_problem = {"problem_number": "1", "text": "1+1=?", "choices": None, "notes": None}
    fake_answer = {"final_answer": "2", "solution_steps": ["1+1=2"], "notes": None}

    with patch("mathauto.pipeline.extractor.extract_problem", return_value=fake_problem), patch(
        "mathauto.pipeline.extractor.extract_answer", return_value=fake_answer
    ):
        result = pipeline.run_build(source, output_source=output_source, use_vision_classifier=False)

    assert len(result.match_report.pairs) == 1
    assert not result.extraction_failures
    assert result.entries_built == 1
    assert result.output_location is not None
    output_path = Path(result.output_location)
    assert output_path.exists()
    assert output_path.suffix == ".pdf"
    assert output_path.stat().st_size > 0


def test_run_build_skips_unmatched_without_crashing(tmp_path):
    (tmp_path / "random_notes.txt").write_bytes(b"not a problem or answer")

    source = LocalFolderSource(tmp_path)
    output_source = LocalFolderSource(tmp_path, output_dir=tmp_path / "out")

    result = pipeline.run_build(source, output_source=output_source, use_vision_classifier=False)

    assert result.entries_built == 0
    assert result.output_location is None
    assert len(result.match_report.unmatched) == 1


def test_run_compile_places_original_images_without_any_ai_call(tmp_path):
    (tmp_path / "01_문제.png").write_bytes(TINY_PNG)
    (tmp_path / "01_정답.png").write_bytes(TINY_PNG)
    (tmp_path / "02_문제.png").write_bytes(TINY_PNG)
    (tmp_path / "02_정답.png").write_bytes(TINY_PNG)

    source = LocalFolderSource(tmp_path)
    output_source = LocalFolderSource(tmp_path, output_dir=tmp_path / "out")

    # No mocking of extractor/anthropic at all: run_compile must not touch the network.
    result = pipeline.run_compile(source, output_source=output_source, use_vision_classifier=False)

    assert len(result.match_report.pairs) == 2
    assert result.entries_built == 2
    assert result.output_location is not None
    output_path = Path(result.output_location)
    assert output_path.exists()
    assert output_path.suffix == ".pdf"
    assert output_path.stat().st_size > 0
