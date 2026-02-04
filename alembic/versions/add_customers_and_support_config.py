"""Add customers and tenant_customer_support_configs tables

Creates tables for customer management and customer support agent configuration.
- customers: Verified existing customers synced from Jackrabbit
- tenant_customer_support_configs: Configuration for dedicated support AI agent

Revision ID: add_customers_and_support_config
Revises: add_admin_notification_tracking
Create Date: 2026-02-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_customers_and_support_config'
down_revision: Union[str, None] = 'add_admin_notification_tracking'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create customers table
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=True),
        sa.Column('jackrabbit_customer_id', sa.Integer(), nullable=True),
        sa.Column('external_customer_id', sa.String(100), nullable=True),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('phone', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='active'),
        sa.Column('account_type', sa.String(50), nullable=True),
        sa.Column('account_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('sync_source', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ),
        sa.ForeignKeyConstraint(['jackrabbit_customer_id'], ['jackrabbit_customers.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_customers_id', 'customers', ['id'], unique=False)
    op.create_index('ix_customers_tenant_id', 'customers', ['tenant_id'], unique=False)
    op.create_index('ix_customers_contact_id', 'customers', ['contact_id'], unique=False)
    op.create_index('ix_customers_jackrabbit_customer_id', 'customers', ['jackrabbit_customer_id'], unique=False)
    op.create_index('ix_customers_external_customer_id', 'customers', ['external_customer_id'], unique=False)
    op.create_index('ix_customers_email', 'customers', ['email'], unique=False)
    op.create_index('ix_customers_phone', 'customers', ['phone'], unique=False)
    op.create_index('ix_customers_tenant_phone', 'customers', ['tenant_id', 'phone'], unique=True)
    op.create_index('ix_customers_tenant_external_id', 'customers', ['tenant_id', 'external_customer_id'], unique=False)

    # Create tenant_customer_support_configs table
    op.create_table(
        'tenant_customer_support_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('telnyx_agent_id', sa.String(255), nullable=True),
        sa.Column('telnyx_phone_number', sa.String(50), nullable=True),
        sa.Column('telnyx_messaging_profile_id', sa.String(255), nullable=True),
        sa.Column('telnyx_api_key', sa.LargeBinary(), nullable=True),  # Encrypted
        sa.Column('support_sms_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('support_voice_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('routing_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('handoff_mode', sa.String(50), nullable=False, server_default='take_message'),
        sa.Column('transfer_number', sa.String(50), nullable=True),
        sa.Column('system_prompt_override', sa.Text(), nullable=True),
        sa.Column('settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index('ix_tenant_customer_support_configs_id', 'tenant_customer_support_configs', ['id'], unique=False)
    op.create_index('ix_tenant_customer_support_configs_tenant_id', 'tenant_customer_support_configs', ['tenant_id'], unique=True)


def downgrade() -> None:
    # Drop tenant_customer_support_configs
    op.drop_index('ix_tenant_customer_support_configs_tenant_id', table_name='tenant_customer_support_configs')
    op.drop_index('ix_tenant_customer_support_configs_id', table_name='tenant_customer_support_configs')
    op.drop_table('tenant_customer_support_configs')

    # Drop customers
    op.drop_index('ix_customers_tenant_external_id', table_name='customers')
    op.drop_index('ix_customers_tenant_phone', table_name='customers')
    op.drop_index('ix_customers_phone', table_name='customers')
    op.drop_index('ix_customers_email', table_name='customers')
    op.drop_index('ix_customers_external_customer_id', table_name='customers')
    op.drop_index('ix_customers_jackrabbit_customer_id', table_name='customers')
    op.drop_index('ix_customers_contact_id', table_name='customers')
    op.drop_index('ix_customers_tenant_id', table_name='customers')
    op.drop_index('ix_customers_id', table_name='customers')
    op.drop_table('customers')
