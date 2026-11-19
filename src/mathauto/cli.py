from __future__ import annotations

import argparse
import json
import sys

from . import pipeline
from .sources import DriveFolderSource, FileSource, LocalFolderSource


def _parse_source(spec: str, credentials: str | None) -> FileSource:
    kind, _, value = spec.partition(":")
    if kind == "local":
        return LocalFolderSource(value)
    if kind == "drive":
        if not credentials:
            raise SystemExit("drive 소스를 쓰려면 --credentials <서비스계정 json 경로> 가 필요합니다")
        return DriveFolderSource(value, credentials)
    raise SystemExit(f"알 수 없는 --source 형식: {spec!r} (local:<경로> 또는 drive:<폴더ID>)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mathauto")
    sub = parser.add_subparsers(dest="command", required=True)

    match_p = sub.add_parser("match", help="실제 생성 없이 문제/정답 매칭 결과만 확인 (dry run)")
    match_p.add_argument("--source", required=True, help="local:<경로> 또는 drive:<폴더ID>")
    match_p.add_argument("--credentials", help="구글 드라이브 서비스 계정 json 경로 (source가 drive일 때 필요)")
    match_p.add_argument(
        "--no-vision-classify",
        action="store_true",
        help="이름만으로 역할을 알 수 없는 파일에 대해 Vision 분류 호출을 생략 (더 빠르지만 모호한 채로 남음)",
    )
    match_p.add_argument("--format", choices=["md", "json"], default="md")

    compile_p = sub.add_parser(
        "compile", help="매칭 -> 원본 사진 그대로 PDF에 배치 -> 업로드 (텍스트 재추출 없음, API 비용 최소)"
    )
    compile_p.add_argument("--source", required=True, help="local:<경로> 또는 drive:<폴더ID>")
    compile_p.add_argument(
        "--output", help="local:<경로> 또는 drive:<폴더ID>; 생략하면 --source와 같은 곳에 저장"
    )
    compile_p.add_argument("--credentials", help="구글 드라이브 서비스 계정 json 경로 (source/output이 drive일 때 필요)")
    compile_p.add_argument("--title", default="문제집")
    compile_p.add_argument("--output-name", default="workbook.pdf")
    compile_p.add_argument("--no-vision-classify", action="store_true")

    build_p = sub.add_parser("build", help="매칭 -> Vision으로 텍스트 재추출 -> PDF 생성 -> 업로드까지 전체 실행")
    build_p.add_argument("--source", required=True, help="local:<경로> 또는 drive:<폴더ID>")
    build_p.add_argument(
        "--output", help="local:<경로> 또는 drive:<폴더ID>; 생략하면 --source와 같은 곳에 저장"
    )
    build_p.add_argument("--credentials", help="구글 드라이브 서비스 계정 json 경로 (source/output이 drive일 때 필요)")
    build_p.add_argument("--title", default="문제집")
    build_p.add_argument("--output-name", default="workbook.pdf")
    build_p.add_argument("--no-vision-classify", action="store_true")

    return parser


def _print_result_common(match_report, entries_built, output_location):
    print(match_report.to_markdown())
    print()
    print(f"생성된 문제 수: {entries_built}")
    if output_location:
        print(f"저장 위치: {output_location}")
    else:
        print("생성된 문제가 없어 PDF를 만들지 않았습니다.")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "match":
        source = _parse_source(args.source, args.credentials)
        report = pipeline.run_match(source, use_vision_classifier=not args.no_vision_classify)
        if args.format == "json":
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(report.to_markdown())
        return 0

    if args.command == "compile":
        source = _parse_source(args.source, args.credentials)
        output_source = _parse_source(args.output, args.credentials) if args.output else source
        result = pipeline.run_compile(
            source,
            output_source=output_source,
            title=args.title,
            output_name=args.output_name,
            use_vision_classifier=not args.no_vision_classify,
        )
        _print_result_common(result.match_report, result.entries_built, result.output_location)
        return 0

    if args.command == "build":
        source = _parse_source(args.source, args.credentials)
        output_source = _parse_source(args.output, args.credentials) if args.output else source
        result = pipeline.run_build(
            source,
            output_source=output_source,
            title=args.title,
            output_name=args.output_name,
            use_vision_classifier=not args.no_vision_classify,
        )
        print(result.match_report.to_markdown())
        print()
        print(f"생성된 문제 수: {result.entries_built}")
        if result.extraction_failures:
            print(f"추출 실패: {len(result.extraction_failures)}건")
            for f in result.extraction_failures:
                print(f"  - [{f.stage}] {f.file_name}: {f.error}")
        if result.output_location:
            print(f"저장 위치: {result.output_location}")
        else:
            print("생성된 문제가 없어 PDF를 만들지 않았습니다.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
