"""add company ai_provider column

Revision ID: d7e8f9a0b1c2
Revises: c1a2b3d4e5f6
Create Date: 2026-08-15 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('ai_provider', sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'ai_provider')
