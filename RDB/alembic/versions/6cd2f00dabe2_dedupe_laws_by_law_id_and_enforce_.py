"""dedupe laws by law_id and enforce unique law_id

Revision ID: 6cd2f00dabe2
Revises: b714fd4ea8de
Create Date: 2026-09-09 00:40:26.082439

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6cd2f00dabe2'
down_revision: Union[str, Sequence[str], None] = 'b714fd4ea8de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 동일 law_id가 여러 행으로 흩어진 경우(법령 개정으로 mst가 바뀌어 upsert가
    # 새 행을 만든 사례), 가장 최신 공포일(동률이면 최신 수집시각) 행만 남기고
    # 나머지는 정리한다.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, law_id,
                   row_number() OVER (
                       PARTITION BY law_id
                       ORDER BY promulgation_date DESC NULLS LAST, fetched_at DESC
                   ) AS rn
            FROM laws
        ),
        stale AS (
            SELECT id FROM ranked WHERE rn > 1
        )
        DELETE FROM law_relations
        WHERE parent_law_id IN (SELECT id FROM stale)
           OR child_law_id IN (SELECT id FROM stale)
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, law_id,
                   row_number() OVER (
                       PARTITION BY law_id
                       ORDER BY promulgation_date DESC NULLS LAST, fetched_at DESC
                   ) AS rn
            FROM laws
        ),
        stale AS (
            SELECT id FROM ranked WHERE rn > 1
        )
        DELETE FROM law_articles WHERE law_id IN (SELECT id FROM stale)
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT id, law_id,
                   row_number() OVER (
                       PARTITION BY law_id
                       ORDER BY promulgation_date DESC NULLS LAST, fetched_at DESC
                   ) AS rn
            FROM laws
        ),
        stale AS (
            SELECT id FROM ranked WHERE rn > 1
        )
        DELETE FROM laws WHERE id IN (SELECT id FROM stale)
        """
    )

    op.alter_column("laws", "law_id", existing_type=sa.String(length=10), nullable=False)
    op.create_unique_constraint("laws_law_id_key", "laws", ["law_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("laws_law_id_key", "laws", type_="unique")
    op.alter_column("laws", "law_id", existing_type=sa.String(length=10), nullable=True)
