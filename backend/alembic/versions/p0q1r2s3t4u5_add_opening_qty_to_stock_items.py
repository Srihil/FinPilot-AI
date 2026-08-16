"""add opening_qty to tally_stock_items

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-08-16 22:30:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = 'p0q1r2s3t4u5'
down_revision: Union[str, None] = 'o9p0q1r2s3t4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tally_stock_items',
                  sa.Column('opening_qty', sa.Float, server_default='0'))


def downgrade() -> None:
    op.drop_column('tally_stock_items', 'opening_qty')
