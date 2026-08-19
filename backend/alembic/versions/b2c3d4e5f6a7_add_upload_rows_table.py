"""add upload_rows table for per-row outcome tracking

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE uploadrowstatus AS ENUM ('pending', 'imported', 'failed')")
    op.create_table(
        'upload_rows',
        sa.Column('id',           sa.UUID(as_uuid=True), primary_key=True),
        sa.Column('upload_id',    sa.UUID(as_uuid=True), sa.ForeignKey('uploads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('row_number',   sa.Integer, nullable=False),
        sa.Column('entity_type',  sa.String(100)),
        sa.Column('status',       sa.Enum('pending', 'imported', 'failed', name='uploadrowstatus'), default='pending'),
        sa.Column('error_reason', sa.Text, nullable=True),
        sa.Column('raw_data',     sa.JSON, nullable=True),
        sa.Column('tally_job_id', sa.UUID(as_uuid=True), sa.ForeignKey('tally_integration_jobs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True)),
        sa.Column('updated_at',   sa.DateTime(timezone=True)),
    )
    op.create_index('ix_upload_rows_upload_id',    'upload_rows', ['upload_id'])
    op.create_index('ix_upload_rows_status',       'upload_rows', ['status'])
    op.create_index('ix_upload_rows_tally_job_id', 'upload_rows', ['tally_job_id'])


def downgrade() -> None:
    op.drop_index('ix_upload_rows_tally_job_id', 'upload_rows')
    op.drop_index('ix_upload_rows_status',       'upload_rows')
    op.drop_index('ix_upload_rows_upload_id',    'upload_rows')
    op.drop_table('upload_rows')
    op.execute("DROP TYPE uploadrowstatus")
