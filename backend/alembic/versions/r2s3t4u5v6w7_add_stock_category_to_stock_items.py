"""add stock_category to tally_stock_items

Revision ID: r2s3t4u5v6w7
Revises: q1r2s3t4u5v6
Create Date: 2026-08-16 23:30:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'r2s3t4u5v6w7'
down_revision: Union[str, None] = 'q1r2s3t4u5v6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='tally_stock_items'"
    ))}
    if 'stock_category' not in existing:
        op.add_column('tally_stock_items', sa.Column('stock_category', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('tally_stock_items', 'stock_category')
