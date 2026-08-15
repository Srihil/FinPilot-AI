"""add CANCEL_VOUCHER to tallyjoboperation enum

Revision ID: j4k5l6m7n8o9
Revises: i3j4k5l6m7n8
Create Date: 2026-08-15 23:30:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'j4k5l6m7n8o9'
down_revision: Union[str, None] = 'i3j4k5l6m7n8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS 'CANCEL_VOUCHER'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — downgrade is a no-op.
    pass
