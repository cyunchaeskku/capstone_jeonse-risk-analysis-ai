"""
법령 RDB 데이터를 LangChain FAISS 벡터DB로 변환한다.

실행:
    python scripts/make_vectorDB.py
    python scripts/make_vectorDB.py --dry-run
    python scripts/make_vectorDB.py --limit 200
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Select, select

# 프로젝트 루트를 sys.path에 추가 (backend.app 모듈 import용)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_openai import OpenAIEmbeddings
try:
    from langchain_community.vectorstores import FAISS
except ImportError:  # pragma: no cover - fallback for older LangChain installs
    from langchain.vectorstores import FAISS

from backend.app.db import SessionLocal
from backend.app.models.law import Law, LawArticle
from backend.app.settings import settings

DEFAULT_OUT_DIR = PROJECT_ROOT / "vectorDB" / "laws_faiss"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_BATCH_SIZE = 100


@dataclass
class VectorDoc:
    doc_id: str
    page_content: str
    metadata: dict


def build_select(limit: int | None) -> Select:
    stmt = (
        select(Law, LawArticle)
        .join(LawArticle, Law.id == LawArticle.law_id)
        .order_by(Law.id.asc(), LawArticle.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return stmt


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    lines = [line.strip() for line in value.splitlines()]
    compact = "\n".join(line for line in lines if line)
    return compact.strip()


def build_citation_label(law_name: str, article_number: str | None, jo_code: str | None) -> str:
    article_ref = article_number or jo_code or "조문미상"
    return f"{law_name} {article_ref}".strip()


def make_doc_id(law_pk: int, article_pk: int, jo_code: str | None) -> str:
    if jo_code:
        return f"law:{law_pk}:jo:{jo_code}"
    return f"law:{law_pk}:article:{article_pk}"


def build_page_content(law: Law, article: LawArticle) -> str:
    law_name = clean_text(law.name)
    article_number = clean_text(article.article_number)
    title = clean_text(article.title)
    body = clean_text(article.full_text)

    sections = [
        f"법령명: {law_name}",
        f"법령구분: {law.category or ''}".rstrip(),
        f"공포일: {law.promulgation_date.isoformat() if law.promulgation_date else ''}".rstrip(),
        f"시행일: {law.enforcement_date.isoformat() if law.enforcement_date else ''}".rstrip(),
        f"조문번호: {article_number}",
        f"조문제목: {title}".rstrip(),
        "본문:",
        body,
    ]
    return "\n".join(sections).strip()


def build_metadata(law: Law, article: LawArticle) -> dict:
    citation_label = build_citation_label(law.name, article.article_number, article.jo_code)
    return {
        "source_type": "law_article",
        "law_pk": law.id,
        "law_mst": law.mst,
        "law_id_external": law.law_id,
        "law_name": law.name,
        "law_category": law.category,
        "promulgation_date": law.promulgation_date.isoformat() if law.promulgation_date else None,
        "enforcement_date": law.enforcement_date.isoformat() if law.enforcement_date else None,
        "article_pk": article.id,
        "jo_code": article.jo_code,
        "article_number": article.article_number,
        "article_title": article.title,
        "citation_label": citation_label,
        "updated_at": law.updated_at.isoformat() if law.updated_at else None,
        "chunk_index": 0,
        "chunk_count": 1,
    }


def load_docs(limit: int | None) -> list[VectorDoc]:
    session = SessionLocal()
    docs: list[VectorDoc] = []
    seen_doc_ids: set[str] = set()

    try:
        rows = session.execute(build_select(limit)).all()
        for law, article in rows:
            doc_id = make_doc_id(law.id, article.id, article.jo_code)
            if doc_id in seen_doc_ids:
                doc_id = f"{doc_id}:article:{article.id}"
            seen_doc_ids.add(doc_id)

            metadata = build_metadata(law, article)
            metadata["doc_id"] = doc_id

            docs.append(
                VectorDoc(
                    doc_id=doc_id,
                    page_content=build_page_content(law, article),
                    metadata=metadata,
                )
            )
    finally:
        session.close()

    return docs


def ensure_out_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_artifacts(
    out_dir: Path,
    docs: list[VectorDoc],
    vectorstore: FAISS,
    model: str,
) -> None:
    ensure_out_dir(out_dir)

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

    embedding_dimension = vectorstore.index.d
    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "embedding_model": model,
        "embedding_dimension": embedding_dimension,
        "document_count": len(docs),
        "source": {
            "database_url": settings.database_url,
            "tables": ["laws", "law_articles"],
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
    parser = argparse.ArgumentParser(description="법령 RDB -> LangChain FAISS 벡터DB 생성")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="출력 디렉터리")
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="OpenAI embedding 모델명",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="임베딩 API 배치 크기",
    )
    parser.add_argument("--limit", type=int, help="개발용: 최대 문서 수")
    parser.add_argument("--dry-run", action="store_true", help="인덱스 생성 없이 통계만 출력")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)

    print("RDB 조문 로드 중...")
    docs = load_docs(limit=args.limit)

    if not docs:
        print("오류: 벡터화할 조문 데이터가 없습니다.")
        raise SystemExit(1)

    print(f"문서 수: {len(docs)}")
    print(f"샘플 인용: {docs[0].metadata['citation_label']}")

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
