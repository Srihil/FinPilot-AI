"""add is_deleted to invoices and expenses for safe soft-delete

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-08-15 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('invoices', sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('expenses', sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    op.drop_column('invoices', 'is_deleted')
    op.drop_column('expenses', 'is_deleted')
