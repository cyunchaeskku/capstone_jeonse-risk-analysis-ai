"""관련성 분류에서 선별된 판례의 전문을 수집해 JSONL로 저장한다.

실행:
    python scripts/collect_precedent_texts.py
    python scripts/collect_precedent_texts.py --label core --label related
    python scripts/collect_precedent_texts.py --dry-run
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

from collect_precedent_summaries import call_korean_law

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RELEVANCE = PROJECT_ROOT / "data" / "precedent_relevance.jsonl"
DEFAULT_SUMMARIES = PROJECT_ROOT / "data" / "precedent_summaries.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "precedent_texts.jsonl"

METADATA_FIELDS = ("case_name", "case_number", "court", "decision_date", "decision_type", "source_url")


def load_targets(relevance_path: Path, summaries_path: Path, labels: list[str]) -> list[dict]:
    with summaries_path.open(encoding="utf-8") as file:
        summaries = {json.loads(line)["precedent_id"]: json.loads(line) for line in file if line.strip()}

    targets = []
    with relevance_path.open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            row = json.loads(line)
            if row["label"] not in labels:
                continue
            summary = summaries[row["precedent_id"]]
            targets.append(
                {
                    "precedent_id": row["precedent_id"],
                    "label": row["label"],
                    **{field: summary.get(field, "") for field in METADATA_FIELDS},
                }
            )
    return targets


def saved_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    with output_path.open(encoding="utf-8") as file:
        return {json.loads(line)["precedent_id"] for line in file if line.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(description="선별된 판례의 전문 수집")
    parser.add_argument("--relevance", type=Path, default=DEFAULT_RELEVANCE, help="관련성 분류 결과 JSONL")
    parser.add_argument("--summaries", type=Path, default=DEFAULT_SUMMARIES, help="요약 JSONL (메타데이터 출처)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="전문 JSONL 출력 경로")
    parser.add_argument("--label", action="append", help="수집할 label (기본: core)")
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 대상 건수만 출력")
    args = parser.parse_args()

    labels = args.label or ["core"]
    targets = load_targets(args.relevance, args.summaries, labels)
    remaining = [target for target in targets if target["precedent_id"] not in saved_ids(args.output)]
    print(f"label {labels} 대상 {len(targets)}건, 미수집 {len(remaining)}건")

    if args.dry_run:
        return

    lengths = []
    failed = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as file:
        for index, target in enumerate(remaining, start=1):
            precedent_id = target["precedent_id"]
            print(f"전문: {index}/{len(remaining)} — {precedent_id}")
            try:
                target["text"] = call_korean_law("get_precedent_text", "--id", precedent_id)
            except RuntimeError as error:
                print(f"  [오류] {precedent_id}: {error}", file=sys.stderr)
                failed += 1
                continue
            file.write(json.dumps(target, ensure_ascii=False) + "\n")
            file.flush()
            lengths.append(len(target["text"]))

    if lengths:
        print(f"전문 길이(자): 중앙값 {statistics.median(lengths):.0f}, 최소 {min(lengths)}, 최대 {max(lengths)}")
    print(f"저장 {len(lengths)}건, 실패 {failed}건, 출력: {args.output}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
