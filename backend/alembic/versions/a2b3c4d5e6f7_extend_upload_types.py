"""extend uploadtype enum with tally master entity types

Revision ID: a2b3c4d5e6f7
Revises: f2a3b4c5d6e7
Create Date: 2026-08-15 23:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_VALUES = ['ledgers', 'stock_groups', 'units', 'godowns']


def upgrade() -> None:
    for val in NEW_VALUES:
        op.execute(f"ALTER TYPE uploadtype ADD VALUE IF NOT EXISTS '{val}'")


def downgrade() -> None:
    pass
