"""merge heads: j4k5l6m7n8o9 and l6m7n8o9p0q1

Revision ID: m7n8o9p0q1r2
Revises: j4k5l6m7n8o9, l6m7n8o9p0q1
Create Date: 2026-08-16 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'm7n8o9p0q1r2'
down_revision: Union[str, tuple] = ('j4k5l6m7n8o9', 'l6m7n8o9p0q1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass  # merge only — no schema changes


def downgrade() -> None:
    pass
