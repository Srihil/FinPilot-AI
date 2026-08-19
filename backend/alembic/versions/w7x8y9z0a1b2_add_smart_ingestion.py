"""add smart ingestion fields to uploads + upload_column_cache table

Revision ID: w7x8y9z0a1b2
Revises: v6w7x8y9z0a1
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'w7x8y9z0a1b2'
down_revision: Union[str, None] = 'v6w7x8y9z0a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_UPLOAD_TYPES = ['stock_items', 'stock_categories', 'vouchers']


def upgrade() -> None:
    # Extend uploadtype enum with new entity types
    for val in NEW_UPLOAD_TYPES:
        op.execute(f"ALTER TYPE uploadtype ADD VALUE IF NOT EXISTS '{val}'")

    # Smart ingestion metadata columns on uploads table
    op.add_column('uploads', sa.Column('detected_entity_type', sa.String(100), nullable=True))
    op.add_column('uploads', sa.Column('entity_confidence', sa.String(20), nullable=True))
    op.add_column('uploads', sa.Column('entity_subtype', sa.String(100), nullable=True))
    op.add_column('uploads', sa.Column('column_mapping', sa.JSON(), nullable=True))
    op.add_column('uploads', sa.Column('header_pattern_key', sa.String(64), nullable=True))
    op.add_column('uploads', sa.Column('pending_rows', sa.JSON(), nullable=True))
    op.add_column('uploads', sa.Column('row_report', sa.JSON(), nullable=True))
    op.add_column('uploads', sa.Column('commit_summary', sa.JSON(), nullable=True))

    # Column mapping cache (saves confirmed header-pattern → entity-type per company)
    op.create_table(
        'upload_column_cache',
        sa.Column('id', sa.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', sa.UUID(as_uuid=True), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False),
        sa.Column('header_fingerprint', sa.String(64), nullable=False),
        sa.Column('entity_type', sa.String(100), nullable=False),
        sa.Column('column_mapping', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('company_id', 'header_fingerprint', name='uq_col_cache_company_fp'),
    )
    op.create_index('ix_upload_col_cache_company', 'upload_column_cache', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_upload_col_cache_company', 'upload_column_cache')
    op.drop_table('upload_column_cache')
    op.drop_column('uploads', 'commit_summary')
    op.drop_column('uploads', 'row_report')
    op.drop_column('uploads', 'pending_rows')
    op.drop_column('uploads', 'header_pattern_key')
    op.drop_column('uploads', 'column_mapping')
    op.drop_column('uploads', 'entity_subtype')
    op.drop_column('uploads', 'entity_confidence')
    op.drop_column('uploads', 'detected_entity_type')
