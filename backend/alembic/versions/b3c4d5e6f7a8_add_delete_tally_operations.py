"""add delete tally job operations

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-08-16 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_VALUES = [
    'DELETE_LEDGER',
    'DELETE_STOCK_ITEM',
    'DELETE_STOCK_GROUP',
    'DELETE_UNIT',
    'DELETE_GODOWN',
]


def upgrade() -> None:
    for val in NEW_VALUES:
        op.execute(f"ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS '{val}'")


def downgrade() -> None:
    pass
