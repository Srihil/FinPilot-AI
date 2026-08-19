"""fix uploadtype enum: add uppercase variants for enum values added as lowercase

The initial migration created the uploadtype enum with UPPERCASE values
(CUSTOMERS, VENDORS, etc.). Later migrations incorrectly added new values
in lowercase (stock_items, stock_categories, vouchers, ledgers, stock_groups,
units, godowns). SQLAlchemy serialises Python enum members by NAME (uppercase),
so the lowercase entries are never matched. This migration adds the missing
UPPERCASE variants.

Revision ID: z0a1b2c3d4e5
Revises: y9z0a1b2c3d4
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'z0a1b2c3d4e5'
down_revision: Union[str, None] = 'y9z0a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MISSING_UPPERCASE = [
    'LEDGERS', 'STOCK_GROUPS', 'UNITS', 'GODOWNS',
    'STOCK_ITEMS', 'STOCK_CATEGORIES', 'VOUCHERS',
]


def upgrade() -> None:
    for val in MISSING_UPPERCASE:
        op.execute(f"ALTER TYPE uploadtype ADD VALUE IF NOT EXISTS '{val}'")


def downgrade() -> None:
    pass
