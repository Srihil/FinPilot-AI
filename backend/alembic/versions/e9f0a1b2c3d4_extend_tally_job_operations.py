"""extend tally job operations for full TallyPrime entity support

Revision ID: e9f0a1b2c3d4
Revises: d7e8f9a0b1c2
Create Date: 2026-08-15 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_VALUES = [
    'CREATE_GROUP',
    'CREATE_STOCK_GROUP',
    'CREATE_UNIT',
    'CREATE_GODOWN',
    'CREATE_JOURNAL_VOUCHER',
    'CREATE_CREDIT_NOTE',
    'CREATE_DEBIT_NOTE',
    'CREATE_CONTRA_VOUCHER',
]


def upgrade() -> None:
    for val in NEW_VALUES:
        op.execute(f"ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS '{val}'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
