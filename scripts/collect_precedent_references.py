"""보유 판례의 참조판례를 따라가 새 판례 요약을 수집한다(눈덩이 표집).

판례 검색은 사건명 위주 매칭이라 쟁점으로는 못 찾는다. 참조판례는 대법원이 직접 인용한
것이므로 법리 연결이 보장된다. 사건번호를 알면 --caseNumber로 정확 조회가 된다.

출력 형식은 collect_precedent_summaries.py와 같아서 classify_precedent_relevance.py에
그대로 넣을 수 있다. search_targets에는 인용한 쪽 사건번호가 들어간다.

실행:
    python scripts/collect_precedent_references.py --dry-run
    python scripts/collect_precedent_references.py
    python scripts/collect_precedent_references.py --case-number 2005다4529 --case-number 2012다33174
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.collect_precedent_summaries import (  # noqa: E402
    call_korean_law,
    parse_search_output,
    saved_ids,
)

DEFAULT_SOURCE = PROJECT_ROOT / "data" / "precedent_texts.jsonl"
DEFAULT_SEEN = PROJECT_ROOT / "data" / "precedent_summaries.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "precedent_references.jsonl"

# 참조판례 섹션은 "대법원 2005. 6. 9. 선고 2005다4529 판결(공2005하,1132)" 형태로 나열된다.
# 사건부호를 열거하지 않으면 "13조와제14", "17조의2" 같은 조문 인용이 사건번호로 잡힌다. 긴 것 먼저.
CASE_CODES = (
    "재다|재도|재두|가단|가합|가소|고단|고합|고정|구단|구합|드단|드합|카기|카합|민상|형상|"
    "다|도|두|나|노|누|마|므|그|후|허|추|초|감"
)
CASE_NUMBER = re.compile(rf"\d{{2,4}}(?:{CASE_CODES})\d{{1,6}}")
SECTION = re.compile(r"참조판례(.{0,4000})", re.S)
YEAR_MIN, YEAR_MAX = 1950, 2026


def normalize_year(case_number: str) -> int | None:
    """사건번호 앞자리를 서기 연도로. 범위 밖이면 None(단기 표기·파싱 쓰레기)."""
    digits = re.match(r"\d{2,4}", case_number).group()
    year = int(digits)
    if len(digits) == 2:
        year += 1900 if year > 50 else 2000
    return year if YEAR_MIN <= year <= YEAR_MAX else None


def case_numbers(paths: list[Path]) -> set[str]:
    numbers = set()
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as file:
            numbers |= {json.loads(line).get("case_number", "").strip() for line in file if line.strip()}
    return numbers - {""}


def extract_references(source_path: Path, held: set[str] | None = None) -> dict[str, list[str]]:
    """사건번호 -> 그것을 인용한 판례 사건번호 목록."""
    references: dict[str, list[str]] = {}
    with source_path.open(encoding="utf-8") as file:
        rows = [json.loads(line) for line in file if line.strip()]

    held = (held or set()) | {(row.get("case_number") or "").strip() for row in rows}
    for row in rows:
        section = SECTION.search(row.get("text") or "")
        if not section:
            continue
        citing = (row.get("case_number") or "").strip()
        for cited in set(CASE_NUMBER.findall(section.group(1))):
            if cited in held or normalize_year(cited) is None:
                continue
            references.setdefault(cited, []).append(citing)
    return references


def lookup(case_number: str) -> dict | None:
    """사건번호 정확 조회. 동명이 여러 건이면 첫 건만."""
    text = call_korean_law(
        "search_precedents", "--caseNumber", case_number, "--display", "5", allow_no_results=True
    )
    _, results = parse_search_output(text)
    return next((r for r in results if (r.get("case_number") or "").strip() == case_number), None)


def main() -> None:
    parser = argparse.ArgumentParser(description="참조판례 눈덩이 수집")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="참조판례를 뽑을 원문 JSONL")
    parser.add_argument(
        "--seen",
        type=Path,
        action="append",
        help=f"이미 가진 JSONL(중복 방지). 반복 지정 가능. 기본 {DEFAULT_SEEN.name}",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="출력 JSONL")
    parser.add_argument("--case-number", action="append", help="참조판례 대신 지정한 사건번호만 수집")
    parser.add_argument("--max-length", type=int, default=1000, help="판례 요약 최대 길이")
    parser.add_argument("--limit", type=int, help="개발용: 앞에서 N건만")
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 후보만 집계")
    args = parser.parse_args()

    seen_paths = args.seen or [DEFAULT_SEEN]
    if args.case_number:
        references = {number: ["수동 지정"] for number in args.case_number}
    else:
        references = extract_references(args.source, case_numbers(seen_paths))
    print(f"참조판례 후보 {len(references)}건 (보유 제외)")

    done_numbers = set()
    if args.output.exists():
        with args.output.open(encoding="utf-8") as file:
            done_numbers = {json.loads(line)["case_number"] for line in file if line.strip()}
    targets = [number for number in sorted(references) if number not in done_numbers]
    if args.limit:
        targets = targets[: args.limit]
    print(f"이미 수집 {len(done_numbers)}건, 이번 대상 {len(targets)}건")

    if args.dry_run:
        for number in targets[:10]:
            print(f"  {number}  ← 인용: {', '.join(references[number][:3])}")
        return

    seen_ids = saved_ids(args.output)
    for path in seen_paths:
        seen_ids |= saved_ids(path)
    found = skipped = failed = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as file:
        for index, number in enumerate(targets, start=1):
            print(f"{index}/{len(targets)} {number}", flush=True)
            try:
                entry = lookup(number)
            except RuntimeError as error:
                print(f"  [오류] 조회 실패: {error}", file=sys.stderr)
                failed += 1
                continue
            if entry is None:
                skipped += 1
                continue
            if entry["precedent_id"] in seen_ids:
                skipped += 1
                continue

            try:
                entry["summary"] = call_korean_law(
                    "summarize_precedent", "--id", entry["precedent_id"], "--maxLength", str(args.max_length)
                )
            except RuntimeError as error:
                print(f"  [오류] 요약 실패: {error}", file=sys.stderr)
                failed += 1
                continue

            entry["search_targets"] = [{"keyword": citing, "category": "reference"} for citing in references[number]]
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            file.flush()
            seen_ids.add(entry["precedent_id"])
            found += 1

    print(f"수집 {found}건, 건너뜀 {skipped}건, 실패 {failed}건, 출력: {args.output}")


if __name__ == "__main__":
    main()
