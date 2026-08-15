"""add tally_groups table and orders tables

Revision ID: g1h2i3j4k5l6
Revises: f2a3b4c5d6e7
Create Date: 2026-08-15 21:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, None] = 'k5l6m7n8o9p0'  # merge migration
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tally_groups ────────────────────────────────────────────────────────────
    op.create_table(
        'tally_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('parent', sa.String(length=255), nullable=True),
        sa.Column('nature', sa.String(length=50), nullable=True),
        sa.Column('tally_key', sa.String(length=512), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=True, server_default='tally_sync'),
        sa.Column('tally_job_id', sa.UUID(), nullable=True),
        sa.Column('tally_sync_status', sa.String(length=50), nullable=True, server_default='pending'),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tally_groups_company_id', 'tally_groups', ['company_id'])

    # ── orders ──────────────────────────────────────────────────────────────────
    op.create_table(
        'orders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('order_number', sa.String(length=100), nullable=False),
        sa.Column('order_type', sa.String(length=20), nullable=False),  # SALES | PURCHASE
        sa.Column('party_name', sa.String(length=500), nullable=True),
        sa.Column('party_ledger', sa.String(length=500), nullable=True),
        sa.Column('order_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('total_amount', sa.Numeric(15, 2), nullable=True, server_default='0'),
        sa.Column('narration', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=True, server_default='DRAFT'),
        sa.Column('tally_sync_status', sa.String(length=50), nullable=True, server_default='local_only'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_orders_company_id', 'orders', ['company_id'])
    op.create_index('ix_orders_order_type', 'orders', ['order_type'])

    # ── order_items ──────────────────────────────────────────────────────────────
    op.create_table(
        'order_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('stock_item_name', sa.String(length=500), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Numeric(15, 3), nullable=True, server_default='1'),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('unit_price', sa.Numeric(15, 2), nullable=True, server_default='0'),
        sa.Column('amount', sa.Numeric(15, 2), nullable=True, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'])


def downgrade() -> None:
    op.drop_index('ix_order_items_order_id', table_name='order_items')
    op.drop_table('order_items')
    op.drop_index('ix_orders_order_type', table_name='orders')
    op.drop_index('ix_orders_company_id', table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_tally_groups_company_id', table_name='tally_groups')
    op.drop_table('tally_groups')
