"""add tally_remote_id to all master tables for TallyPrime MASTERID storage

Revision ID: y9z0a1b2c3d4
Revises: x8y9z0a1b2c3
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'y9z0a1b2c3d4'
down_revision: Union[str, None] = 'x8y9z0a1b2c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MASTER_TABLES = [
    'tally_ledgers',
    'tally_stock_groups',
    'tally_units',
    'tally_godowns',
    'tally_stock_items',
    'tally_groups',
]


def upgrade() -> None:
    for table in MASTER_TABLES:
        op.add_column(table, sa.Column('tally_remote_id', sa.String(100), nullable=True))


def downgrade() -> None:
    for table in MASTER_TABLES:
        op.drop_column(table, 'tally_remote_id')
