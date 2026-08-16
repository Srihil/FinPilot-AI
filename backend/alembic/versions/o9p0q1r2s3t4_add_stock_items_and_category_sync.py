"""add tally_stock_items table and tally sync fields to stock_categories

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-08-16 19:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = 'o9p0q1r2s3t4'
down_revision: Union[str, None] = 'n8o9p0q1r2s3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Create tally_stock_items table if it doesn't exist
    if not conn.dialect.has_table(conn, 'tally_stock_items'):
        op.create_table(
            'tally_stock_items',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
            sa.Column('name', sa.String(500), nullable=False),
            sa.Column('stock_group', sa.String(255), nullable=True),
            sa.Column('unit', sa.String(50), nullable=True),
            sa.Column('rate', sa.Float, server_default='0'),
            sa.Column('tally_key', sa.String(512), nullable=False),
            sa.Column('source', sa.String(50), server_default='tally_sync'),
            sa.Column('tally_job_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('tally_sync_status', sa.String(50), server_default='pending'),
            sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('conflict_data', postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column('conflict_detected_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('is_active', sa.Boolean, server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True)),
            sa.Column('updated_at', sa.DateTime(timezone=True)),
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_tally_stock_items_company_id ON tally_stock_items (company_id)")

    # Add Tally sync fields to stock_categories (skip if column already exists)
    existing_cols = {row[0] for row in conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='stock_categories'"
    ))}
    if 'tally_key' not in existing_cols:
        op.add_column('stock_categories', sa.Column('tally_key', sa.String(512), nullable=True))
    if 'source' not in existing_cols:
        op.add_column('stock_categories', sa.Column('source', sa.String(50), server_default='finpilot'))
    if 'tally_job_id' not in existing_cols:
        op.add_column('stock_categories', sa.Column('tally_job_id', postgresql.UUID(as_uuid=True), nullable=True))
    if 'tally_sync_status' not in existing_cols:
        op.add_column('stock_categories', sa.Column('tally_sync_status', sa.String(50), server_default='pending'))
    if 'synced_at' not in existing_cols:
        op.add_column('stock_categories', sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True))

    # Add new enum values for CREATE_STOCK_CATEGORY and DELETE_STOCK_CATEGORY
    op.execute("ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS 'CREATE_STOCK_CATEGORY'")
    op.execute("ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS 'DELETE_STOCK_CATEGORY'")


def downgrade() -> None:
    op.drop_column('stock_categories', 'synced_at')
    op.drop_column('stock_categories', 'tally_sync_status')
    op.drop_column('stock_categories', 'tally_job_id')
    op.drop_column('stock_categories', 'source')
    op.drop_column('stock_categories', 'tally_key')
    op.drop_index('ix_tally_stock_items_company_id', 'tally_stock_items')
    op.drop_table('tally_stock_items')
