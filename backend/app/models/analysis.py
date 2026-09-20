from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class Analysis(Base):
    """위험도 분석 1건. 비로그인 분석도 남기므로 user_id는 NULL을 허용한다."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    listing_name: Mapped[str] = mapped_column(String(200), nullable=False)
    deposit_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 0이면 시세 미확보. RiskAssessRequest와 같은 규약이다.
    market_price_krw: Mapped[int] = mapped_column(BigInteger, nullable=False)
    risk_grade: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_score: Mapped[int] = mapped_column(nullable=False)
    # 규칙이 늘 때마다 마이그레이션하지 않도록 입력·결과 원본은 JSONB로 둔다.
    request: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), index=True
    )
