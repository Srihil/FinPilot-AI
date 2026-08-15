"""merge branch heads: c4d5e6f7a8b9 and f2a3b4c5d6e7

Both branches exist in production:
  - c4d5e6f7a8b9: add is_deleted to invoices/expenses
  - f2a3b4c5d6e7: add tally master tables (ledgers, stock groups, units, godowns)

This merge migration makes them a single head so alembic upgrade head works.

Revision ID: k5l6m7n8o9p0
Revises: c4d5e6f7a8b9, f2a3b4c5d6e7
Create Date: 2026-08-15 23:45:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'k5l6m7n8o9p0'
down_revision: Union[str, tuple] = ('c4d5e6f7a8b9', 'f2a3b4c5d6e7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass   # merge only — no schema changes


def downgrade() -> None:
    pass
