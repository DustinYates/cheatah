"""Add tenant_prompt_configs table for JSON-based prompt system

Revision ID: add_tenant_prompt_config
Revises: add_prompt_channel
Create Date: 2026-01-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'add_tenant_prompt_config'
down_revision = 'add_prompt_channel'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenant_prompt_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('schema_version', sa.String(50), nullable=False, server_default='bss_chatbot_prompt_v1'),
        sa.Column('business_type', sa.String(50), nullable=False, server_default='bss'),
        sa.Column('config_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', name='uq_tenant_prompt_configs_tenant_id')
    )
    op.create_index('ix_tenant_prompt_configs_id', 'tenant_prompt_configs', ['id'])
    op.create_index('ix_tenant_prompt_configs_tenant_id', 'tenant_prompt_configs', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_tenant_prompt_configs_tenant_id', table_name='tenant_prompt_configs')
    op.drop_index('ix_tenant_prompt_configs_id', table_name='tenant_prompt_configs')
    op.drop_table('tenant_prompt_configs')
