"""add tally master tables (ledgers, stock groups, units, godowns)

Revision ID: f2a3b4c5d6e7
Revises: e9f0a1b2c3d4
Create Date: 2026-08-15 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e9f0a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tally_ledgers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('parent_group', sa.String(length=255), nullable=True),
        sa.Column('opening_balance', sa.Float(), nullable=True, server_default='0'),
        sa.Column('closing_balance', sa.Float(), nullable=True, server_default='0'),
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
    op.create_index('ix_tally_ledgers_company_id', 'tally_ledgers', ['company_id'])

    op.create_table(
        'tally_stock_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('parent', sa.String(length=255), nullable=True),
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
    op.create_index('ix_tally_stock_groups_company_id', 'tally_stock_groups', ['company_id'])

    op.create_table(
        'tally_units',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=True),
        sa.Column('decimal_places', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('unit_type', sa.String(length=20), nullable=True, server_default='simple'),
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
    op.create_index('ix_tally_units_company_id', 'tally_units', ['company_id'])

    op.create_table(
        'tally_godowns',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=500), nullable=False),
        sa.Column('parent', sa.String(length=255), nullable=True),
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
    op.create_index('ix_tally_godowns_company_id', 'tally_godowns', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_tally_godowns_company_id', table_name='tally_godowns')
    op.drop_table('tally_godowns')

    op.drop_index('ix_tally_units_company_id', table_name='tally_units')
    op.drop_table('tally_units')

    op.drop_index('ix_tally_stock_groups_company_id', table_name='tally_stock_groups')
    op.drop_table('tally_stock_groups')

    op.drop_index('ix_tally_ledgers_company_id', table_name='tally_ledgers')
    op.drop_table('tally_ledgers')
