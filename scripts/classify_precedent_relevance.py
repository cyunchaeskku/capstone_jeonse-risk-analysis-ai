"""판례 요약을 LLM에 읽혀 전세사기 예방 프로젝트와의 관련성을 분류한다.

실행:
    python scripts/classify_precedent_relevance.py --dry-run
    python scripts/classify_precedent_relevance.py --limit 100
    python scripts/classify_precedent_relevance.py
    python scripts/classify_precedent_relevance.py --model gpt-4.1-mini --output data/precedent_relevance_mini.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (backend.app 모듈 import용)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from backend.app.settings import settings

DEFAULT_INPUT = PROJECT_ROOT / "data" / "precedent_summaries.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "precedent_relevance.jsonl"
DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_BATCH_SIZE = 10
LABELS = {"core", "related", "unrelated"}

SYSTEM_PROMPT = """
너는 전세사기 예방 서비스의 법률 RAG 데이터를 선별한다.
판례 요약 목록을 받아 각각을 전세(주택 임대차) 보증금 피해와 얼마나 관련 있는지 분류한다.

label 기준:
- core: 주택 임대차 보증금이 직접 쟁점이다. 보증금 반환, 대항력·우선변제권·확정일자, 임차권등기,
  소액임차인 최우선변제, 경매·배당에서 임차인의 지위, 전세보증금 편취 사기, 임대인이나 공인중개사의 책임,
  깡통전세·갭투자·신탁을 이용한 전세사기가 여기 해당한다.
- related: 주택 임대차가 직접 쟁점은 아니지만 전세 위험을 판단할 때 쓰이는 법리다.
  근저당권과 채권최고액, 사해행위취소, 배당순위, 명의신탁, 조세채권의 우선순위,
  사기죄의 기망행위나 고의 판단 기준, 상가 임대차가 여기 해당한다.
- unrelated: 그 외 전부.

판단 규칙:
- 요약은 길이 제한 때문에 중간에 잘려 있을 수 있다. 보이는 범위에서만 판단한다.
- core인지 related인지 애매하면 related로 둔다. 관련 없어 보이면 주저 말고 unrelated로 둔다.
- 사건명만 보고 판단하지 말고 요약 내용을 근거로 삼는다.

출력은 아래 형식의 JSON 객체 하나다. 입력에 있는 모든 항목을 입력 순서 그대로, 하나도 빠짐없이 넣는다.
{"results": [{"precedent_id": "입력에 있는 값 그대로", "label": "core 또는 related 또는 unrelated", "reason": "한국어 30자 이내 근거"}]}
""".strip()


def load_rows(input_path: Path, limit: int | None) -> tuple[list[dict], int]:
    """본문(판시사항/판결요지) 없이 머리말만 있는 요약은 판단 근거가 없으므로 제외한다."""
    with input_path.open(encoding="utf-8") as file:
        rows = [json.loads(line) for line in file if line.strip()]
    with_body = [row for row in rows if "판시사항" in row["summary"] or "판결요지" in row["summary"]]
    dropped = len(rows) - len(with_body)
    return (with_body[:limit] if limit else with_body), dropped


def done_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    with output_path.open(encoding="utf-8") as file:
        return {json.loads(line)["precedent_id"] for line in file if line.strip()}


def build_user_prompt(batch: list[dict]) -> str:
    items = [
        {"precedent_id": row["precedent_id"], "case_name": row["case_name"], "summary": row["summary"]}
        for row in batch
    ]
    return json.dumps(items, ensure_ascii=False)


def classify_batch(model: ChatOpenAI, batch: list[dict]) -> list[dict]:
    response = model.invoke(
        [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=build_user_prompt(batch))]
    )
    results = json.loads(response.content)["results"]

    by_id = {result["precedent_id"]: result for result in results}
    if by_id.keys() != {row["precedent_id"] for row in batch}:
        raise RuntimeError(f"응답 ID 불일치 (요청 {len(batch)}건, 응답 {len(by_id)}건)")

    for row in batch:
        result = by_id[row["precedent_id"]]
        if result["label"] not in LABELS:
            raise RuntimeError(f"알 수 없는 label: {result['label']}")
        result["case_name"] = row["case_name"]
    return [by_id[row["precedent_id"]] for row in batch]


def main() -> None:
    parser = argparse.ArgumentParser(description="판례 요약의 전세사기 관련성 LLM 분류")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="요약 JSONL 입력 경로")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="분류 결과 JSONL 출력 경로")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI 모델명")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="한 번에 보낼 요약 수")
    parser.add_argument("--limit", type=int, help="입력 앞에서 N건만 처리 (기준 프롬프트 검수용)")
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 첫 배치 프롬프트만 출력")
    args = parser.parse_args()

    rows, dropped = load_rows(args.input, args.limit)
    remaining = [row for row in rows if row["precedent_id"] not in done_ids(args.output)]
    print(f"대상 {len(rows)}건(본문 없어 제외 {dropped}건), 미분류 {len(remaining)}건, 모델 {args.model}")

    batches = [remaining[index : index + args.batch_size] for index in range(0, len(remaining), args.batch_size)]

    if args.dry_run:
        print(f"호출 예정 {len(batches)}회")
        if batches:
            print(f"--- 첫 배치 프롬프트 ---\n{build_user_prompt(batches[0])[:2000]}")
        return

    if not settings.openai_api_key or not settings.openai_api_key.strip():
        print("오류: OPENAI_API_KEY가 설정되지 않았습니다.")
        raise SystemExit(1)

    model = ChatOpenAI(
        model=args.model,
        api_key=settings.openai_api_key,
        temperature=0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    labels = Counter()
    failed = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as file:
        for index, batch in enumerate(batches, start=1):
            print(f"분류: {index}/{len(batches)}")
            try:
                results = classify_batch(model, batch)
            except (RuntimeError, KeyError, json.JSONDecodeError) as error:
                print(f"  [오류] {error}", file=sys.stderr)
                failed += 1
                continue
            for result in results:
                file.write(json.dumps(result, ensure_ascii=False) + "\n")
                labels[result["label"]] += 1
            file.flush()

    print(f"분류 완료: {dict(labels)}, 실패 배치 {failed}건, 출력: {args.output}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
