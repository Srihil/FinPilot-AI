"""add stock_categories and stock_transactions tables

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-08-15 22:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'h2i3j4k5l6m7'
down_revision: Union[str, None] = 'g1h2i3j4k5l6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── stock_categories ─────────────────────────────────────────────────────
    op.create_table(
        'stock_categories',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('parent', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stock_categories_company_id', 'stock_categories', ['company_id'])

    # ── stock_transactions ────────────────────────────────────────────────────
    op.create_table(
        'stock_transactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('transaction_number', sa.String(length=100), nullable=False),
        sa.Column('transaction_type', sa.String(length=50), nullable=False),
        sa.Column('transaction_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('narration', sa.Text(), nullable=True),
        sa.Column('party_name', sa.String(length=500), nullable=True),
        sa.Column('from_godown', sa.String(length=500), nullable=True),
        sa.Column('to_godown', sa.String(length=500), nullable=True),
        sa.Column('entries', sa.JSON(), nullable=True),
        sa.Column('tally_sync_status', sa.String(length=50), nullable=True, server_default='local_only'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stock_transactions_company_id', 'stock_transactions', ['company_id'])
    op.create_index('ix_stock_transactions_type', 'stock_transactions', ['transaction_type'])

    # ── conflict_data column on tally master tables ───────────────────────────
    for table in ('tally_ledgers', 'tally_stock_groups', 'tally_units', 'tally_godowns', 'tally_groups'):
        op.add_column(table, sa.Column('conflict_data', sa.JSON(), nullable=True))
        op.add_column(table, sa.Column('conflict_detected_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table in ('tally_ledgers', 'tally_stock_groups', 'tally_units', 'tally_godowns', 'tally_groups'):
        op.drop_column(table, 'conflict_detected_at')
        op.drop_column(table, 'conflict_data')
    op.drop_index('ix_stock_transactions_type', table_name='stock_transactions')
    op.drop_index('ix_stock_transactions_company_id', table_name='stock_transactions')
    op.drop_table('stock_transactions')
    op.drop_index('ix_stock_categories_company_id', table_name='stock_categories')
    op.drop_table('stock_categories')
