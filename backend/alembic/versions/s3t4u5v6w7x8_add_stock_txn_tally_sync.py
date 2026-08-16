"""add stock transaction tally sync

Revision ID: s3t4u5v6w7x8
Revises: r2s3t4u5v6w7
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = 's3t4u5v6w7x8'
down_revision: Union[str, None] = 'r2s3t4u5v6w7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add 6 new values to the tallyjoboperation PostgreSQL enum
    for val in [
        'CREATE_STOCK_JOURNAL',
        'CREATE_PHYSICAL_STOCK',
        'CREATE_DELIVERY_NOTE',
        'CREATE_RECEIPT_NOTE',
        'CREATE_REJECTION_IN',
        'CREATE_REJECTION_OUT',
    ]:
        conn.execute(sa.text(f"ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS '{val}'"))

    # Add tally_job_id column to stock_transactions
    existing_cols = {r[0] for r in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='stock_transactions'"
    ))}
    if 'tally_job_id' not in existing_cols:
        op.add_column('stock_transactions', sa.Column('tally_job_id', PG_UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column('stock_transactions', 'tally_job_id')
