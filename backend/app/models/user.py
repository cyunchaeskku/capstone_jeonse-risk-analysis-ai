from datetime import datetime

from sqlalchemy import CHAR, TIMESTAMP, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 대소문자만 다른 중복 가입을 막기 위해 항상 소문자로 정규화해서 넣는다.
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    # argon2id 해시 문자열. 솔트와 파라미터가 이 문자열 안에 함께 들어 있어 별도 컬럼이 없다.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    """로그인 세션 한 건. 토큰 원문은 저장하지 않고 SHA-256 해시만 보관한다."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")
