from datetime import date, datetime

from sqlalchemy import DATE, TEXT, TIMESTAMP, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class Precedent(Base):
    """판례 한 건이 한 행. 임베딩용 청킹은 make_vectorDB_precedents.py에서 파생시킨다."""

    __tablename__ = "precedents"

    # 법제처 판례일련번호
    precedent_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    case_name: Mapped[str] = mapped_column(TEXT, nullable=False)
    case_number: Mapped[str | None] = mapped_column(String(50))
    court: Mapped[str | None] = mapped_column(String(50))
    decision_date: Mapped[date | None] = mapped_column(DATE)
    decision_type: Mapped[str | None] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(TEXT)
    # 관련성 분류 결과: core / related
    label: Mapped[str | None] = mapped_column(String(20))

    holding: Mapped[str | None] = mapped_column(TEXT)  # 판시사항
    summary: Mapped[str | None] = mapped_column(TEXT)  # 판결요지
    referenced_statutes: Mapped[str | None] = mapped_column(TEXT)  # 참조조문
    referenced_precedents: Mapped[str | None] = mapped_column(TEXT)  # 참조판례
    body: Mapped[str | None] = mapped_column(TEXT)  # 전문
    # 섹션 파싱이 틀렸을 때를 위한 API 응답 원본
    raw_text: Mapped[str] = mapped_column(TEXT, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )
