"""
판례 RDB 데이터를 LangChain FAISS 벡터DB로 변환한다.

법령 인덱스(`make_vectorDB_laws.py`)와는 별도 디렉터리에 저장한다. 한 인덱스에 섞으면
유사도 상위 결과가 한쪽 소스로 쏠려서, 법령 근거와 판례가 둘 다 필요한 답변이 망가진다.

청킹 전략:
    판시사항(holding) / 판결요지(summary) - 자르지 않고 1청크
    전문(body)                            - 1,000자 / overlap 150자
    참조조문 / 참조판례                    - 임베딩하지 않음 (필요하면 DB에서 조회)

실행:
    python scripts/make_vectorDB_precedents.py
    python scripts/make_vectorDB_precedents.py --dry-run
    python scripts/make_vectorDB_precedents.py --label core --label related
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

# 프로젝트 루트를 sys.path에 추가 (backend.app 모듈 import용)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from langchain_community.vectorstores import FAISS
except ImportError:  # pragma: no cover - fallback for older LangChain installs
    from langchain.vectorstores import FAISS

from backend.app.db import SessionLocal
from backend.app.models.precedent import Precedent
from backend.app.settings import settings

DEFAULT_OUT_DIR = PROJECT_ROOT / "vectorDB" / "precedents_faiss"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"  # settings.vector_db_embedding_model과 맞춘다
DEFAULT_BATCH_SIZE = 100
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150

# 사건명이 죄명 나열로 100자를 넘는 경우가 있다. 청크마다 그대로 붙이면 본문 임베딩이
# 죄명 목록에 희석되므로 머리말에서는 잘라 쓰고, 전체 값은 메타데이터에 남긴다.
CASE_NAME_HEAD_LIMIT = 60


@dataclass
class VectorDoc:
    doc_id: str
    page_content: str
    metadata: dict


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    lines = [line.strip() for line in value.splitlines()]
    compact = "\n".join(line for line in lines if line)
    return compact.strip()


def build_citation_label(precedent: Precedent) -> str:
    parts = [precedent.court, precedent.case_number]
    return " ".join(part for part in parts if part).strip() or precedent.precedent_id


def build_header(precedent: Precedent, section: str) -> str:
    case_name = clean_text(precedent.case_name)
    if len(case_name) > CASE_NAME_HEAD_LIMIT:
        case_name = case_name[:CASE_NAME_HEAD_LIMIT] + "…"

    decided = precedent.decision_date.isoformat() if precedent.decision_date else ""
    return "\n".join(
        [
            f"판례: {build_citation_label(precedent)}",
            f"선고일: {decided} {precedent.decision_type or ''}".rstrip(),
            f"사건명: {case_name}",
            f"구분: {section}",
        ]
    )


def split_body(body: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_text(body)


def build_docs_for_precedent(
    precedent: Precedent,
    chunk_size: int,
    chunk_overlap: int,
) -> list[VectorDoc]:
    """판시사항/판결요지는 통째로, 전문만 잘라서 청크 목록을 만든다."""
    pieces: list[tuple[str, str, list[str]]] = []  # (section, key, chunk texts)

    holding = clean_text(precedent.holding)
    if holding:
        pieces.append(("판시사항", "holding", [holding]))

    summary = clean_text(precedent.summary)
    if summary:
        pieces.append(("판결요지", "summary", [summary]))

    body = clean_text(precedent.body)
    if body:
        pieces.append(("전문", "body", split_body(body, chunk_size, chunk_overlap)))

    citation_label = build_citation_label(precedent)
    docs: list[VectorDoc] = []
    for section, key, chunks in pieces:
        for index, chunk in enumerate(chunks):
            doc_id = f"prec:{precedent.precedent_id}:{key}:{index}"
            docs.append(
                VectorDoc(
                    doc_id=doc_id,
                    page_content=f"{build_header(precedent, section)}\n{chunk}",
                    metadata={
                        "source_type": "precedent",
                        "precedent_id": precedent.precedent_id,
                        "citation_label": citation_label,
                        "case_name": precedent.case_name,
                        "case_number": precedent.case_number,
                        "court": precedent.court,
                        "decision_date": (
                            precedent.decision_date.isoformat()
                            if precedent.decision_date
                            else None
                        ),
                        "decision_type": precedent.decision_type,
                        "source_url": precedent.source_url,
                        "section": section,
                        "chunk_index": index,
                        "chunk_count": len(chunks),
                        "doc_id": doc_id,
                    },
                )
            )
    return docs


def load_docs(labels: list[str], chunk_size: int, chunk_overlap: int, limit: int | None):
    session = SessionLocal()
    try:
        stmt = (
            select(Precedent)
            .where(Precedent.label.in_(labels))
            .order_by(Precedent.decision_date.desc(), Precedent.precedent_id.asc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        precedents = list(session.execute(stmt).scalars())
    finally:
        session.close()

    docs: list[VectorDoc] = []
    for precedent in precedents:
        docs.extend(build_docs_for_precedent(precedent, chunk_size, chunk_overlap))
    return precedents, docs


def print_stats(precedents: list[Precedent], docs: list[VectorDoc]) -> None:
    by_section: dict[str, list[int]] = {}
    for doc in docs:
        by_section.setdefault(doc.metadata["section"], []).append(len(doc.page_content))

    print(f"판례 {len(precedents)}건 -> 청크 {len(docs)}개")
    for section in ("판시사항", "판결요지", "전문"):
        lengths = by_section.get(section)
        if not lengths:
            continue
        ordered = sorted(lengths)
        print(
            f"  {section}: {len(lengths)}청크, 길이 중앙값 {ordered[len(ordered) // 2]}자, "
            f"최대 {ordered[-1]}자"
        )

    without_body = [p.precedent_id for p in precedents if not clean_text(p.body)]
    if without_body:
        print(f"  [경고] 전문 없음 {len(without_body)}건: {without_body[:5]}")


def save_artifacts(out_dir: Path, docs: list[VectorDoc], vectorstore: FAISS, model: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    docs_path = out_dir / "documents.jsonl"
    id_map_path = out_dir / "id_map.json"
    manifest_path = out_dir / "manifest.json"

    vectorstore.save_local(str(out_dir))

    with docs_path.open("w", encoding="utf-8") as f:
        for doc in docs:
            line = {
                "doc_id": doc.doc_id,
                "page_content": doc.page_content,
                "metadata": doc.metadata,
            }
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    id_map = {str(k): v for k, v in vectorstore.index_to_docstore_id.items()}
    id_map_path.write_text(json.dumps(id_map, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "embedding_model": model,
        "embedding_dimension": vectorstore.index.d,
        "document_count": len(docs),
        "source": {
            "database_url": settings.database_url,
            "tables": ["precedents"],
        },
        "files": {
            "index": "index.faiss",
            "docstore": "index.pkl",
            "documents": docs_path.name,
            "id_map": id_map_path.name,
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="판례 RDB -> LangChain FAISS 벡터DB 생성")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="출력 디렉터리")
    parser.add_argument(
        "--label",
        action="append",
        help="인덱싱할 관련성 라벨 (기본 core, 반복 지정 가능)",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="OpenAI embedding 모델명",
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="임베딩 API 배치 크기")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="전문 청크 크기(자)")
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help="전문 청크 겹침(자)",
    )
    parser.add_argument("--limit", type=int, help="개발용: 최대 판례 수")
    parser.add_argument("--dry-run", action="store_true", help="인덱스 생성 없이 통계만 출력")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    labels = args.label or ["core"]

    print(f"RDB 판례 로드 중... (label={', '.join(labels)})")
    precedents, docs = load_docs(labels, args.chunk_size, args.chunk_overlap, args.limit)

    if not docs:
        print("오류: 벡터화할 판례 데이터가 없습니다.")
        raise SystemExit(1)

    print_stats(precedents, docs)
    print(f"샘플 인용: {docs[0].metadata['citation_label']} ({docs[0].doc_id})")

    if args.dry_run:
        print("dry-run 완료 (임베딩/저장 생략)")
        return

    if not settings.openai_api_key or not settings.openai_api_key.strip():
        print("오류: OPENAI_API_KEY가 설정되지 않았습니다.")
        raise SystemExit(1)

    print("임베딩/인덱스 생성 중...")
    embeddings = OpenAIEmbeddings(
        model=args.embedding_model,
        api_key=settings.openai_api_key,
        chunk_size=args.batch_size,
    )

    vectorstore = FAISS.from_texts(
        texts=[doc.page_content for doc in docs],
        embedding=embeddings,
        metadatas=[doc.metadata for doc in docs],
        ids=[doc.doc_id for doc in docs],
    )

    print("산출물 저장 중...")
    save_artifacts(out_dir=out_dir, docs=docs, vectorstore=vectorstore, model=args.embedding_model)

    print("완료")
    print(f"- out_dir: {out_dir}")
    print(f"- index.ntotal: {vectorstore.index.ntotal}")


if __name__ == "__main__":
    main()
