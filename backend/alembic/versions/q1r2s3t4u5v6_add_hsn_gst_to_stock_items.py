"""add hsn_code, gst_rate, type_of_supply to tally_stock_items

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-08-16 23:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'q1r2s3t4u5v6'
down_revision: Union[str, None] = 'p0q1r2s3t4u5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='tally_stock_items'"
    ))}
    if 'hsn_code' not in existing:
        op.add_column('tally_stock_items', sa.Column('hsn_code', sa.String(50), nullable=True))
    if 'gst_rate' not in existing:
        op.add_column('tally_stock_items', sa.Column('gst_rate', sa.Float, nullable=True))
    if 'type_of_supply' not in existing:
        op.add_column('tally_stock_items', sa.Column('type_of_supply', sa.String(20), server_default='Goods'))


def downgrade() -> None:
    op.drop_column('tally_stock_items', 'type_of_supply')
    op.drop_column('tally_stock_items', 'gst_rate')
    op.drop_column('tally_stock_items', 'hsn_code')
