"""add tally_voucher_ref and tally_sync_status to invoices and expenses

Revision ID: i3j4k5l6m7n8
Revises: h2i3j4k5l6m7
Create Date: 2026-08-15 23:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'i3j4k5l6m7n8'
down_revision: Union[str, None] = 'h2i3j4k5l6m7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # invoices table
    op.add_column('invoices',
        sa.Column('tally_voucher_ref', sa.String(length=100), nullable=True))
    op.add_column('invoices',
        sa.Column('tally_sync_status', sa.String(length=50), nullable=True,
                  server_default='local_only'))

    # expenses table
    op.add_column('expenses',
        sa.Column('tally_voucher_ref', sa.String(length=100), nullable=True))
    op.add_column('expenses',
        sa.Column('tally_sync_status', sa.String(length=50), nullable=True,
                  server_default='local_only'))


def downgrade() -> None:
    op.drop_column('expenses', 'tally_sync_status')
    op.drop_column('expenses', 'tally_voucher_ref')
    op.drop_column('invoices', 'tally_sync_status')
    op.drop_column('invoices', 'tally_voucher_ref')
