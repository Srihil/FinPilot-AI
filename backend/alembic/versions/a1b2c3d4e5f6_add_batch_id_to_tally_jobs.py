"""add batch_id to tally_integration_jobs for bulk import grouping

Revision ID: a1b2c3d4e5f6
Revises: z0a1b2c3d4e5
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'z0a1b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tally_integration_jobs',
        sa.Column('batch_id', sa.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_tally_jobs_batch_id', 'tally_integration_jobs', ['batch_id'])


def downgrade() -> None:
    op.drop_index('ix_tally_jobs_batch_id', 'tally_integration_jobs')
    op.drop_column('tally_integration_jobs', 'batch_id')
