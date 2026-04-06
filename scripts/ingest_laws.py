"""
법령 데이터 수집 스크립트

korean-law CLI를 통해 법령 전문을 가져와 PostgreSQL DB에 저장한다.
수집 대상은 scripts/law_targets.yaml 에서 관리한다.

실행:
    python scripts/ingest_laws.py                    # 전체 수집
    python scripts/ingest_laws.py --only "부동산등기법"  # 특정 법령만
    python scripts/ingest_laws.py --dry-run          # DB 저장 없이 조회만
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

# 프로젝트 루트를 sys.path에 추가 (backend.app 모듈 import용)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.app.db import SessionLocal
from backend.app.models.law import Law, LawArticle

# get_batch_articles 한 번에 보낼 최대 조문 수
BATCH_CHUNK_SIZE = 50


# ---------------------------------------------------------------------------
# korean-law CLI 호출
# ---------------------------------------------------------------------------

def call_korean_law(*args: str) -> str:
    """korean-law CLI를 호출하고 stdout 텍스트를 반환한다."""
    cmd = ["korean-law", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"korean-law 호출 실패: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )

    raw = result.stdout.strip()
    if not raw:
        raise RuntimeError(f"korean-law 응답이 비어 있음: {' '.join(cmd)}")

    return raw


# ---------------------------------------------------------------------------
# 법령 검색 파싱
# 출력 형식:
#   검색 결과 (총 N건):
#   1. 법령명
#      - 법령ID: XXXXXX
#      - MST: XXXXXX
#      - 공포일: YYYYMMDD
#      - 구분: XX
# ---------------------------------------------------------------------------

def search_law(name: str) -> dict:
    """법령 이름으로 검색해 메타데이터를 반환한다."""
    text = call_korean_law("search_law", "--query", name)
    results = _parse_search_output(text)

    if not results:
        raise ValueError(f"검색 결과 없음: {name!r}\n원본:\n{text[:300]}")

    # 이름 정확 일치 우선, 없으면 첫 번째
    exact = next((r for r in results if r["name"] == name), results[0])
    return exact


def _parse_search_output(text: str) -> list[dict]:
    """
    search_law 텍스트 출력을 파싱해 법령 메타데이터 목록을 반환한다.
    """
    results = []
    # 각 항목은 숫자. 으로 시작하는 블록
    blocks = re.split(r"\n(?=\d+\. )", text)

    for block in blocks:
        lines = block.strip().splitlines()
        if not lines:
            continue

        # 첫 줄: "1. 법령명" 또는 "법령명" (첫 블록)
        first = re.sub(r"^\d+\.\s*", "", lines[0]).strip()
        if not first or "검색 결과" in first:
            continue

        entry = {"name": first}
        for line in lines[1:]:
            line = line.strip().lstrip("- ")
            if line.startswith("법령ID:"):
                entry["law_id"] = line.split(":", 1)[1].strip()
            elif line.startswith("MST:"):
                entry["mst"] = line.split(":", 1)[1].strip()
            elif line.startswith("공포일:"):
                entry["promulgation_date"] = _fmt_date(line.split(":", 1)[1].strip())
            elif line.startswith("시행일:"):
                entry["enforcement_date"] = _fmt_date(line.split(":", 1)[1].strip())
            elif line.startswith("구분:"):
                entry["category"] = line.split(":", 1)[1].strip()

        if "mst" in entry:
            results.append(entry)

    return results


def _fmt_date(value: str) -> str | None:
    """'20231201' → '2023-12-01'"""
    s = value.strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s or None


# ---------------------------------------------------------------------------
# 목차 파싱 → 조문 번호 목록 추출
# 출력 형식:
#   법령명: 부동산등기법
#   ...
#   목차 (총 N개 조문)
#
#   제1조 목적
#   제2조 정의
#   ...
#   특정 조문 조회: ...
# ---------------------------------------------------------------------------

def fetch_article_numbers(mst: str) -> list[str]:
    """get_law_text로 목차를 가져와 조문 번호 목록(예: ['제1조','제2조',...])을 반환한다."""
    text = call_korean_law("get_law_text", "--mst", mst)

    numbers = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(제\d+조(?:의\d+)?)\s", line)
        if m:
            numbers.append(m.group(1))

    return numbers


# ---------------------------------------------------------------------------
# 조문 본문 일괄 조회
# 출력 형식 (get_batch_articles):
#   법령명
#   제1조 목적
#   본문...
#
#   제2조 정의
#   본문...
# ---------------------------------------------------------------------------

def fetch_articles(mst: str) -> list[dict]:
    """
    목차 → 조문 번호 추출 → get_batch_articles 일괄 조회.
    반환: [{jo_code, article_number, title, full_text}, ...]
    """
    numbers = fetch_article_numbers(mst)
    if not numbers:
        raise RuntimeError(f"mst={mst}: 목차에서 조문 번호를 찾지 못했습니다.")

    print(f"  목차 조문 수: {len(numbers)}")

    all_articles = []
    # BATCH_CHUNK_SIZE 단위로 나눠서 조회
    for i in range(0, len(numbers), BATCH_CHUNK_SIZE):
        chunk = numbers[i : i + BATCH_CHUNK_SIZE]
        text = call_korean_law(
            "get_batch_articles",
            "--mst", mst,
            "--articles", json.dumps(chunk, ensure_ascii=False),
        )
        all_articles.extend(_parse_batch_output(text))

    return all_articles


def _parse_batch_output(text: str) -> list[dict]:
    """
    get_batch_articles 텍스트 출력을 파싱해 조문 목록을 반환한다.

    형식:
      법령명          ← 첫 줄 (건너뜀)
      제1조 목적
      본문...
                      ← 빈 줄이 조문 구분자
      제2조 정의
      본문...
    """
    lines = text.splitlines()

    # 첫 줄이 법령명이면 건너뜀 (조문 헤더 패턴이 아닌 경우)
    start = 0
    if lines and not re.match(r"^제\d+조", lines[0].strip()):
        start = 1

    articles = []
    current_header = None
    current_body_lines: list[str] = []

    def flush():
        if current_header is None:
            return
        m = re.match(r"^(제\d+조(?:의\d+)?)\s*(.*)", current_header)
        if not m:
            return
        article_number = m.group(1)
        title = m.group(2).strip() or None
        full_text = "\n".join(current_body_lines).strip()
        articles.append({
            "jo_code": article_number,       # 조문번호를 jo_code로 사용
            "article_number": article_number,
            "title": title,
            "full_text": full_text if full_text else (title or ""),
        })

    for line in lines[start:]:
        stripped = line.strip()
        if re.match(r"^제\d+조(?:의\d+)?[\s\[]", stripped) or re.match(r"^제\d+조$", stripped):
            # 새 조문 시작
            flush()
            current_header = stripped
            current_body_lines = []
        else:
            if current_header is not None:
                current_body_lines.append(line)

    flush()
    return articles


# ---------------------------------------------------------------------------
# DB Upsert
# ---------------------------------------------------------------------------

def upsert_law(session, meta: dict) -> int:
    stmt = (
        pg_insert(Law)
        .values(
            mst=meta["mst"],
            law_id=meta.get("law_id") or None,
            name=meta["name"],
            category=meta.get("category"),
            promulgation_date=meta.get("promulgation_date"),
            enforcement_date=meta.get("enforcement_date"),
        )
        .on_conflict_do_update(
            index_elements=["mst"],
            set_={
                "law_id": meta.get("law_id") or None,
                "name": meta["name"],
                "category": meta.get("category"),
                "promulgation_date": meta.get("promulgation_date"),
                "enforcement_date": meta.get("enforcement_date"),
            },
        )
        .returning(Law.id)
    )
    return session.execute(stmt).scalar_one()


def upsert_articles(session, law_db_id: int, articles: list[dict]) -> int:
    if not articles:
        return 0

    rows = [
        {
            "law_id": law_db_id,
            "jo_code": a["jo_code"],
            "article_number": a["article_number"],
            "title": a["title"],
            "full_text": a["full_text"],
        }
        for a in articles
    ]

    stmt = (
        pg_insert(LawArticle)
        .values(rows)
        .on_conflict_do_update(
            index_elements=["law_id", "jo_code"],
            set_={
                "article_number": pg_insert(LawArticle).excluded.article_number,
                "title": pg_insert(LawArticle).excluded.title,
                "full_text": pg_insert(LawArticle).excluded.full_text,
            },
        )
    )
    session.execute(stmt)
    return len(rows)


# ---------------------------------------------------------------------------
# 메인 수집 로직
# ---------------------------------------------------------------------------

def ingest_one(name: str, dry_run: bool) -> None:
    print(f"\n[{name}] 검색 중...")
    meta = search_law(name)
    print(f"  mst={meta['mst']}, 카테고리={meta.get('category')}, 시행일={meta.get('enforcement_date')}")

    print(f"[{name}] 조문 조회 중...")
    articles = fetch_articles(meta["mst"])
    print(f"  조문 {len(articles)}개 파싱됨")

    if dry_run:
        print("  [dry-run] DB 저장 생략")
        if articles:
            a = articles[0]
            print(f"  샘플 — jo_code={a['jo_code']!r}, title={a['title']!r}")
            print(f"  본문 앞 100자: {a['full_text'][:100]!r}")
        return

    session = SessionLocal()
    try:
        law_db_id = upsert_law(session, meta)
        count = upsert_articles(session, law_db_id, articles)
        session.commit()
        print(f"  저장 완료: laws.id={law_db_id}, 조문 {count}개")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def load_targets(yaml_path: Path) -> list[str]:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [entry["name"] for entry in data["laws"]]


def main() -> None:
    parser = argparse.ArgumentParser(description="법령 데이터 수집 스크립트")
    parser.add_argument("--only", metavar="LAW_NAME", help="특정 법령만 수집")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 조회만")
    args = parser.parse_args()

    yaml_path = Path(__file__).parent / "law_targets.yaml"
    all_targets = load_targets(yaml_path)
    targets = [args.only] if args.only else all_targets

    print(f"수집 대상: {targets}")
    if args.dry_run:
        print("(dry-run 모드: DB에 저장하지 않습니다)")

    errors: list[tuple[str, str]] = []
    for name in targets:
        try:
            ingest_one(name, dry_run=args.dry_run)
        except Exception as e:
            print(f"  [오류] {name}: {e}")
            errors.append((name, str(e)))

    print("\n=== 완료 ===")
    print(f"성공: {len(targets) - len(errors)}/{len(targets)}")
    if errors:
        print("실패 목록:")
        for name, msg in errors:
            print(f"  - {name}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
