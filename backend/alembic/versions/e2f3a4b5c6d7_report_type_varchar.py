"""convert reports.report_type from enum to varchar — allows new report types without enum migrations

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cast enum column to varchar — preserves all existing values
    op.execute(
        "ALTER TABLE reports ALTER COLUMN report_type TYPE VARCHAR(100) "
        "USING report_type::VARCHAR(100)"
    )


def downgrade() -> None:
    # Cannot safely cast back to enum without knowing all current values; no-op
    pass
