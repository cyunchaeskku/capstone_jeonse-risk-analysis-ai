"""수집한 판례 전문(JSONL)을 파싱해 PostgreSQL precedents 테이블에 적재한다.

실행:
    python scripts/ingest_precedents.py
    python scripts/ingest_precedents.py --dry-run
    python scripts/ingest_precedents.py --input data/precedent_texts.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert

# 프로젝트 루트를 sys.path에 추가 (backend.app 모듈 import용)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.db import SessionLocal
from backend.app.models import Precedent

DEFAULT_INPUT = PROJECT_ROOT / "data" / "precedent_texts.jsonl"
SECTION_NAMES = ("기본 정보", "판시사항", "판결요지", "참조조문", "참조판례", "전문")
SECTION_BOUNDARY = "|".join(SECTION_NAMES)


def extract_section(text: str, name: str) -> str | None:
    """CLI 출력에서 한 섹션을 뽑고 <br/> 태그를 줄바꿈으로 되돌린다."""
    match = re.search(rf"\n{name}:\n?(.*?)(?=\n(?:{SECTION_BOUNDARY}):|\Z)", text, re.S)
    if not match:
        return None
    content = re.sub(r"<br\s*/?>", "\n", match.group(1))
    content = re.sub(r"<[^>]+>", "", content)
    return re.sub(r"\n{3,}", "\n\n", content).strip() or None


def parse_decision_date(value: str) -> date | None:
    try:
        return datetime.strptime(value, "%Y.%m.%d").date()
    except ValueError:
        return None


def build_row(record: dict) -> dict:
    text = record["text"]
    return {
        "precedent_id": record["precedent_id"],
        "case_name": record["case_name"],
        "case_number": record.get("case_number"),
        "court": record.get("court"),
        "decision_date": parse_decision_date(record.get("decision_date", "")),
        "decision_type": record.get("decision_type"),
        "source_url": record.get("source_url"),
        "label": record.get("label"),
        "holding": extract_section(text, "판시사항"),
        "summary": extract_section(text, "판결요지"),
        "referenced_statutes": extract_section(text, "참조조문"),
        "referenced_precedents": extract_section(text, "참조판례"),
        "body": extract_section(text, "전문"),
        "raw_text": text,
    }


def upsert(session, row: dict) -> None:
    updatable = {key: value for key, value in row.items() if key != "precedent_id"}
    stmt = (
        pg_insert(Precedent)
        .values(**row)
        .on_conflict_do_update(index_elements=["precedent_id"], set_=updatable)
    )
    session.execute(stmt)


def main() -> None:
    parser = argparse.ArgumentParser(description="판례 전문 JSONL -> PostgreSQL 적재")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="전문 JSONL 입력 경로")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 파싱 결과만 출력")
    args = parser.parse_args()

    with args.input.open(encoding="utf-8") as file:
        rows = [build_row(json.loads(line)) for line in file if line.strip()]

    print(f"입력 {len(rows)}건")
    for field in ("holding", "summary", "referenced_statutes", "referenced_precedents", "body"):
        print(f"  {field}: {sum(row[field] is not None for row in rows)}건 파싱")
    missing_date = [row["precedent_id"] for row in rows if row["decision_date"] is None]
    if missing_date:
        print(f"  [경고] 선고일 파싱 실패 {len(missing_date)}건: {missing_date[:5]}")

    if args.dry_run:
        print("(dry-run 모드: DB에 저장하지 않습니다)")
        return

    session = SessionLocal()
    try:
        for row in rows:
            upsert(session, row)
        session.commit()
    finally:
        session.close()

    print(f"적재 완료 {len(rows)}건")


if __name__ == "__main__":
    main()
