"""판례 검색 결과를 모아 ID별 요약을 JSONL로 저장한다.

실행:
    python scripts/collect_precedent_summaries.py
    python scripts/collect_precedent_summaries.py --only '임대차보증금'
    python scripts/collect_precedent_summaries.py --self-check
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGETS_PATH = Path(__file__).with_name("precedent_targets.yaml")
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "precedent_summaries.jsonl"


def call_korean_law(*args: str, allow_no_results: bool = False) -> str:
    result = subprocess.run(
        ["korean-law", *args], capture_output=True, text=True
    )
    output = result.stdout.strip()
    no_results = output.startswith("검색 결과가 없습니다.")
    if (result.returncode and not (allow_no_results and no_results)) or not output or output.startswith("[EXTERNAL_API_ERROR]"):
        raise RuntimeError(result.stderr.strip() or output or "빈 응답")
    return output


def parse_search_output(text: str) -> tuple[int, list[dict]]:
    total = 0
    if "총 " in text:
        try:
            total = int(text.split("총 ", 1)[1].split("건", 1)[0])
        except ValueError:
            pass

    results = []
    for block in text.split("\n[")[1:]:
        lines = ("[" + block).splitlines()
        precedent_id = lines[0].split("]", 1)[0].lstrip("[")
        if not precedent_id.isdigit():
            continue
        entry = {"precedent_id": precedent_id, "case_name": lines[0].split("]", 1)[1].strip()}
        for line in lines[1:]:
            key, separator, value = line.strip().partition(":")
            if separator and key in {"사건번호", "법원", "선고일", "판결유형", "링크"}:
                entry[{"사건번호": "case_number", "법원": "court", "선고일": "decision_date", "판결유형": "decision_type", "링크": "source_url"}[key]] = value.strip()
        results.append(entry)
    return total, results


def search_precedents(keyword: str, page_size: int) -> list[dict]:
    first = call_korean_law(
        "search_precedents", "--query", keyword, "--display", str(page_size), "--page", "1", allow_no_results=True
    )
    total, results = parse_search_output(first)
    for page in range(2, math.ceil(total / page_size) + 1):
        text = call_korean_law(
            "search_precedents", "--query", keyword, "--display", str(page_size), "--page", str(page), allow_no_results=True
        )
        results.extend(parse_search_output(text)[1])
    return results


def load_targets() -> list[dict]:
    with TARGETS_PATH.open(encoding="utf-8") as file:
        return yaml.safe_load(file)["queries"]


def saved_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    with output_path.open(encoding="utf-8") as file:
        return {json.loads(line)["precedent_id"] for line in file if line.strip()}


def collect_candidates(targets: list[dict], page_size: int) -> dict[str, dict]:
    candidates = {}
    for target in targets:
        keyword = target["keyword"]
        print(f"검색: {keyword}")
        for result in search_precedents(keyword, page_size):
            candidate = candidates.setdefault(result["precedent_id"], result | {"search_targets": []})
            candidate["search_targets"].append(target)
    return candidates


def write_summaries(candidates: dict[str, dict], output_path: Path, max_length: int) -> tuple[int, int]:
    done = saved_ids(output_path)
    remaining = [candidate for precedent_id, candidate in candidates.items() if precedent_id not in done]
    succeeded = 0
    failed = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as file:
        for index, candidate in enumerate(remaining, start=1):
            precedent_id = candidate["precedent_id"]
            print(f"요약: {index}/{len(remaining)} — {precedent_id}")
            try:
                candidate["summary"] = call_korean_law(
                    "summarize_precedent", "--id", precedent_id, "--maxLength", str(max_length)
                )
            except RuntimeError as error:
                print(f"  [오류] {precedent_id}: {error}", file=sys.stderr)
                failed += 1
                continue
            file.write(json.dumps(candidate, ensure_ascii=False) + "\n")
            file.flush()
            succeeded += 1
    return succeeded, failed


def self_check() -> None:
    total, results = parse_search_output(
        "판례 검색 결과 (총 1건, 1페이지):\n\n[226751] 임대차보증금반환\n  사건번호: 2015다59801\n  법원: 대법원\n  선고일: 2021.01.28\n  판결유형: 판결\n  링크: /example"
    )
    assert total == 1 and results[0]["precedent_id"] == "226751"
    assert parse_search_output("검색 결과가 없습니다.") == (0, [])


def main() -> None:
    parser = argparse.ArgumentParser(description="판례 검색 결과의 ID별 요약 수집")
    parser.add_argument("--only", action="append", metavar="KEYWORD", help="특정 검색어만 실행")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="JSONL 출력 경로")
    parser.add_argument("--page-size", type=int, default=100, choices=range(1, 101), metavar="1..100")
    parser.add_argument("--max-length", type=int, default=1000, help="판례 요약 최대 길이")
    parser.add_argument("--self-check", action="store_true", help="외부 API 없이 파서 확인")
    args = parser.parse_args()

    if args.self_check:
        self_check()
        print("self-check passed")
        return

    targets = load_targets()
    if args.only:
        targets = [target for target in targets if target["keyword"] in args.only]
        missing = set(args.only) - {target["keyword"] for target in targets}
        if missing:
            parser.error(f"precedent_targets.yaml에 없는 검색어: {', '.join(sorted(missing))}")

    candidates = collect_candidates(targets, args.page_size)
    succeeded, failed = write_summaries(candidates, args.output, args.max_length)
    print(f"후보 {len(candidates)}건, 새 요약 저장 {succeeded}건, 실패 {failed}건, 출력: {args.output}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
