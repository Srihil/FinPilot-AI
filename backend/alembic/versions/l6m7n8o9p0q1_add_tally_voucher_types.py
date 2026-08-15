"""add tally_voucher_types table and CREATE_VOUCHER_TYPE enum value

Revision ID: l6m7n8o9p0q1
Revises: g1h2i3j4k5l6
Create Date: 2026-08-16 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'l6m7n8o9p0q1'
down_revision: Union[str, None] = 'g1h2i3j4k5l6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add enum value first — must come before any DDL that might reference the type.
    # PostgreSQL 12+ supports ALTER TYPE ... ADD VALUE inside a transaction.
    op.execute("ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS 'CREATE_VOUCHER_TYPE'")

    op.create_table(
        'tally_voucher_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('parent', sa.String(255), nullable=True),
        sa.Column('numbering_method', sa.String(50), nullable=True,
                  server_default='Automatic'),
        sa.Column('tally_key', sa.String(512), nullable=False),
        sa.Column('source', sa.String(50), nullable=True, server_default='tally_sync'),
        sa.Column('tally_job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tally_sync_status', sa.String(50), nullable=True,
                  server_default='pending'),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True,
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tally_voucher_types_company_id', 'tally_voucher_types', ['company_id'])
    op.create_index('ix_tally_voucher_types_tally_key', 'tally_voucher_types', ['tally_key'])


def downgrade() -> None:
    op.drop_index('ix_tally_voucher_types_tally_key', table_name='tally_voucher_types')
    op.drop_index('ix_tally_voucher_types_company_id', table_name='tally_voucher_types')
    op.drop_table('tally_voucher_types')
