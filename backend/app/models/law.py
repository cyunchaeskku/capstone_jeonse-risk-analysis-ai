from datetime import date, datetime

from sqlalchemy import (
    DATE,
    TEXT,
    TIMESTAMP,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


class Law(Base):
    __tablename__ = "laws"

    id: Mapped[int] = mapped_column(primary_key=True)
    mst: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    law_id: Mapped[str | None] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 법률 / 대통령령 / 부령 / 조례 / 규칙
    category: Mapped[str | None] = mapped_column(String(30))
    promulgation_date: Mapped[date | None] = mapped_column(DATE)
    enforcement_date: Mapped[date | None] = mapped_column(DATE)
    fetched_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    articles: Mapped[list["LawArticle"]] = relationship(
        back_populates="law", cascade="all, delete-orphan"
    )
    child_relations: Mapped[list["LawRelation"]] = relationship(
        foreign_keys="LawRelation.parent_law_id",
        back_populates="parent_law",
        cascade="all, delete-orphan",
    )
    parent_relations: Mapped[list["LawRelation"]] = relationship(
        foreign_keys="LawRelation.child_law_id",
        back_populates="child_law",
        cascade="all, delete-orphan",
    )


class LawRelation(Base):
    __tablename__ = "law_relations"
    __table_args__ = (UniqueConstraint("parent_law_id", "child_law_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_law_id: Mapped[int] = mapped_column(ForeignKey("laws.id"), nullable=False)
    child_law_id: Mapped[int] = mapped_column(ForeignKey("laws.id"), nullable=False)
    # 시행령 / 시행규칙 / 위임규정
    relation_type: Mapped[str | None] = mapped_column(String(20))

    parent_law: Mapped["Law"] = relationship(
        foreign_keys=[parent_law_id], back_populates="child_relations"
    )
    child_law: Mapped["Law"] = relationship(
        foreign_keys=[child_law_id], back_populates="parent_relations"
    )


class LawArticle(Base):
    __tablename__ = "law_articles"
    __table_args__ = (UniqueConstraint("law_id", "jo_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    law_id: Mapped[int] = mapped_column(ForeignKey("laws.id"), nullable=False)
    jo_code: Mapped[str | None] = mapped_column(String(10))
    article_number: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(200))
    full_text: Mapped[str] = mapped_column(TEXT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    law: Mapped["Law"] = relationship(back_populates="articles")
