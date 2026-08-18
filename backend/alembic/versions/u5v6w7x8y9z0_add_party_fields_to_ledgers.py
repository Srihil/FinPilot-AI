"""add party fields to ledgers

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa

revision = 'u5v6w7x8y9z0'
down_revision = 't4u5v6w7x8y9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('tally_ledgers', sa.Column('email',   sa.String(255), nullable=True))
    op.add_column('tally_ledgers', sa.Column('phone',   sa.String(50),  nullable=True))
    op.add_column('tally_ledgers', sa.Column('address', sa.String(500), nullable=True))
    op.add_column('tally_ledgers', sa.Column('city',    sa.String(100), nullable=True))
    op.add_column('tally_ledgers', sa.Column('state',   sa.String(100), nullable=True))
    op.add_column('tally_ledgers', sa.Column('gstin',   sa.String(20),  nullable=True))


def downgrade():
    op.drop_column('tally_ledgers', 'gstin')
    op.drop_column('tally_ledgers', 'state')
    op.drop_column('tally_ledgers', 'city')
    op.drop_column('tally_ledgers', 'address')
    op.drop_column('tally_ledgers', 'phone')
    op.drop_column('tally_ledgers', 'email')
