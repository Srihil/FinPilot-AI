"""replace city with country on tally_ledgers

Revision ID: v6w7x8y9z0a1
Revises: u5v6w7x8y9z0
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa

revision = 'v6w7x8y9z0a1'
down_revision = 'u5v6w7x8y9z0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tally_ledgers', sa.Column('country', sa.String(100), nullable=True))
    op.drop_column('tally_ledgers', 'city')


def downgrade():
    op.add_column('tally_ledgers', sa.Column('city', sa.String(100), nullable=True))
    op.drop_column('tally_ledgers', 'country')
