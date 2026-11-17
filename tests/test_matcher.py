from mathauto.matcher import match
from mathauto.sources import SourceFile


def sf(name: str, parent: str = "") -> SourceFile:
    return SourceFile(id=f"{parent}/{name}" if parent else name, name=name, parent_name=parent, mime_type="image/jpeg")


def test_folder_split_with_numbers():
    files = [
        sf("1.jpg", "문제"), sf("2.jpg", "문제"), sf("3.jpg", "문제"),
        sf("1.jpg", "정답"), sf("2.jpg", "정답"), sf("3.jpg", "정답"),
    ]
    report = match(files)
    assert len(report.pairs) == 3
    assert not report.unmatched
    assert not report.ambiguous
    for p in report.pairs:
        assert p.strategy == "folder_split+number"
        assert p.problem.parent_name == "문제"
        assert p.answer.parent_name == "정답"


def test_folder_split_english_order_fallback():
    files = [
        sf("a.png", "problems"), sf("b.png", "problems"), sf("c.png", "problems"),
        sf("x.png", "answers"), sf("y.png", "answers"), sf("z.png", "answers"),
    ]
    report = match(files)
    assert len(report.pairs) == 3
    assert all(p.strategy == "folder_split+order" for p in report.pairs)
    assert not report.unmatched and not report.ambiguous


def test_filename_marker_korean():
    files = [sf("01_문제.jpg"), sf("01_정답.jpg"), sf("02_문제.jpg"), sf("02_정답.jpg")]
    report = match(files)
    assert len(report.pairs) == 2
    assert {p.group_key for p in report.pairs} == {"01", "02"}
    assert all(p.strategy == "filename_marker" for p in report.pairs)


def test_filename_marker_english_word():
    files = [sf("ch3_question.png"), sf("ch3_answer.png")]
    report = match(files)
    assert len(report.pairs) == 1
    pair = report.pairs[0]
    assert pair.problem.name == "ch3_question.png"
    assert pair.answer.name == "ch3_answer.png"


def test_glued_letter_number_marker():
    files = [sf("q1.jpg"), sf("a1.png")]
    report = match(files)
    assert len(report.pairs) == 1
    pair = report.pairs[0]
    assert pair.problem.name == "q1.jpg"
    assert pair.answer.name == "a1.png"


def test_numeric_sequence_needs_vision_classifier():
    files = [sf("1.jpg"), sf("1_b.jpg")]

    def classify(f: SourceFile) -> str:
        return "problem" if f.name == "1.jpg" else "answer"

    report_without_classifier = match(files)
    assert not report_without_classifier.pairs
    assert report_without_classifier.ambiguous

    report_with_classifier = match(files, classify_role_fn=classify)
    assert len(report_with_classifier.pairs) == 1
    pair = report_with_classifier.pairs[0]
    assert pair.strategy == "numeric_sequence+vision"
    assert pair.problem.name == "1.jpg"
    assert pair.answer.name == "1_b.jpg"


def test_ambiguous_same_role_twice():
    files = [sf("1_q.jpg"), sf("1_q.png")]
    report = match(files)
    assert not report.pairs
    assert len(report.ambiguous) == 1
    assert {f.name for f in report.ambiguous[0]} == {"1_q.jpg", "1_q.png"}


def test_unmatched_files():
    files = [sf("01_문제.jpg"), sf("01_정답.jpg"), sf("05_정답.jpg"), sf("random_notes.txt")]
    report = match(files)
    assert len(report.pairs) == 1
    unmatched_names = {f.name for f in report.unmatched}
    assert unmatched_names == {"05_정답.jpg", "random_notes.txt"}
