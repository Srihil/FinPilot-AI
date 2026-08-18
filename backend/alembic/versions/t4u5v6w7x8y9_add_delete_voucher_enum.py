"""add DELETE_VOUCHER to tallyjoboperation enum

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 't4u5v6w7x8y9'
down_revision: Union[str, None] = 's3t4u5v6w7x8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE tallyjoboperation ADD VALUE IF NOT EXISTS 'DELETE_VOUCHER'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values — downgrade is a no-op.
    pass
