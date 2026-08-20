"""add new report types: gst_summary, trial_balance, aged_receivables, aged_payables, customer_statement, vendor_statement

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-08-20
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE reporttype ADD VALUE IF NOT EXISTS 'gst_summary'")
    op.execute("ALTER TYPE reporttype ADD VALUE IF NOT EXISTS 'trial_balance'")
    op.execute("ALTER TYPE reporttype ADD VALUE IF NOT EXISTS 'aged_receivables'")
    op.execute("ALTER TYPE reporttype ADD VALUE IF NOT EXISTS 'aged_payables'")
    op.execute("ALTER TYPE reporttype ADD VALUE IF NOT EXISTS 'customer_statement'")
    op.execute("ALTER TYPE reporttype ADD VALUE IF NOT EXISTS 'vendor_statement'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
