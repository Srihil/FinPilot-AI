"""add DELETE_VOUCHER_TYPE to tallyjoboperation enum

Revision ID: n8o9p0q1r2s3
Revises: m7n8o9p0q1r2
Create Date: 2026-08-16 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'n8o9p0q1r2s3'
down_revision: Union[str, None] = 'm7n8o9p0q1r2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS 'DELETE_VOUCHER_TYPE'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an ENUM type
    pass
