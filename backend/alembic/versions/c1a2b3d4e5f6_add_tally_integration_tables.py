"""add tally integration tables

Revision ID: c1a2b3d4e5f6
Revises: b05e77fbce20
Create Date: 2026-08-14 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = 'b05e77fbce20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tally_connectors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('connector_name', sa.String(length=255), nullable=True),
        sa.Column('device_name', sa.String(length=255), nullable=True),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'DISCONNECTED', 'REVOKED', name='connectorstatus'), nullable=True),
        sa.Column('tally_host', sa.String(length=255), nullable=True),
        sa.Column('tally_port', sa.Integer(), nullable=True),
        sa.Column('tally_company_name', sa.String(length=500), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index('ix_tally_connectors_company_id', 'tally_connectors', ['company_id'])

    op.create_table(
        'tally_pairing_codes',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_used', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('ix_tally_pairing_codes_code', 'tally_pairing_codes', ['code'])
    op.create_index('ix_tally_pairing_codes_company_id', 'tally_pairing_codes', ['company_id'])

    op.create_table(
        'tally_integration_jobs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('connector_id', sa.UUID(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('approval_id', sa.UUID(), nullable=True),
        sa.Column('operation', sa.Enum(
            'READ_COMPANIES', 'READ_LEDGERS', 'READ_VOUCHERS', 'READ_SALES',
            'READ_PURCHASES', 'READ_RECEIVABLES', 'READ_PAYABLES', 'READ_STOCK_ITEMS',
            'CREATE_SALES_VOUCHER', 'CREATE_PURCHASE_VOUCHER', 'CREATE_RECEIPT_VOUCHER',
            'CREATE_PAYMENT_VOUCHER', 'CREATE_LEDGER', 'CREATE_STOCK_ITEM',
            'SYNC_FULL', 'SYNC_PARTIAL',
            name='tallyjoboperation',
        ), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.Enum(
            'PENDING', 'CLAIMED', 'RUNNING', 'SUCCESS', 'FAILED', 'RETRYING', 'CANCELLED',
            name='jobstatus',
        ), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['approval_id'], ['approvals.id']),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['connector_id'], ['tally_connectors.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index('ix_tally_integration_jobs_company_id', 'tally_integration_jobs', ['company_id'])
    op.create_index('ix_tally_integration_jobs_connector_id', 'tally_integration_jobs', ['connector_id'])
    op.create_index('ix_tally_integration_jobs_status', 'tally_integration_jobs', ['status'])
    op.create_index('ix_tally_integration_jobs_created_at', 'tally_integration_jobs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_tally_integration_jobs_created_at', table_name='tally_integration_jobs')
    op.drop_index('ix_tally_integration_jobs_status', table_name='tally_integration_jobs')
    op.drop_index('ix_tally_integration_jobs_connector_id', table_name='tally_integration_jobs')
    op.drop_index('ix_tally_integration_jobs_company_id', table_name='tally_integration_jobs')
    op.drop_table('tally_integration_jobs')

    op.drop_index('ix_tally_pairing_codes_company_id', table_name='tally_pairing_codes')
    op.drop_index('ix_tally_pairing_codes_code', table_name='tally_pairing_codes')
    op.drop_table('tally_pairing_codes')

    op.drop_index('ix_tally_connectors_company_id', table_name='tally_connectors')
    op.drop_table('tally_connectors')

    op.execute("DROP TYPE IF EXISTS connectorstatus")
    op.execute("DROP TYPE IF EXISTS tallyjoboperation")
    op.execute("DROP TYPE IF EXISTS jobstatus")
