"""Add jackrabbit API key columns to tenant_customer_service_configs

Revision ID: add_jackrabbit_api_keys
Revises: b97c37dd6ee5
Create Date: 2026-01-31

Adds encrypted columns for storing per-tenant Jackrabbit CRM API keys,
which are passed to Zapier webhooks for class schedule lookups.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_jackrabbit_api_keys'
down_revision = 'b97c37dd6ee5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tenant_customer_service_configs',
        sa.Column('jackrabbit_api_key_1', sa.String(length=765), nullable=True),
    )
    op.add_column(
        'tenant_customer_service_configs',
        sa.Column('jackrabbit_api_key_2', sa.String(length=765), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tenant_customer_service_configs', 'jackrabbit_api_key_2')
    op.drop_column('tenant_customer_service_configs', 'jackrabbit_api_key_1')
