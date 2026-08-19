"""add pg_trgm extension and trigram indexes for fuzzy name matching

Revision ID: x8y9z0a1b2c3
Revises: w7x8y9z0a1b2
Create Date: 2026-08-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'x8y9z0a1b2c3'
down_revision: Union[str, None] = 'w7x8y9z0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables and their name columns that benefit from trigram indexes
TRGM_TARGETS = [
    ('tally_ledgers',      'name'),
    ('tally_stock_items',  'name'),
    ('tally_stock_groups', 'name'),
    ('tally_groups',       'name'),
    ('tally_units',        'name'),
    ('stock_categories',   'name'),
]


def upgrade() -> None:
    # pg_trgm enables word_similarity() and GIN indexes used for fuzzy name matching.
    # The extension must be created by a superuser; this is a no-op if already present.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    for table, col in TRGM_TARGETS:
        idx_name = f"idx_trgm_{table}_{col}"
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {table} USING gin(lower({col}) gin_trgm_ops)"
        )


def downgrade() -> None:
    for table, col in TRGM_TARGETS:
        idx_name = f"idx_trgm_{table}_{col}"
        op.execute(f"DROP INDEX IF EXISTS {idx_name}")
    # Do NOT drop pg_trgm — other parts of the DB may depend on it.
