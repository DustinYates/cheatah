"""Add tenant widget config table

Revision ID: add_widget_config
Revises: add_email_lead_prefixes
Create Date: 2025-12-26

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_widget_config'
down_revision = 'add_email_lead_prefixes'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tenant_widget_configs table
    op.create_table(
        'tenant_widget_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index(op.f('ix_tenant_widget_configs_id'), 'tenant_widget_configs', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_widget_configs_tenant_id'), 'tenant_widget_configs', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_widget_configs_tenant_id'), table_name='tenant_widget_configs')
    op.drop_index(op.f('ix_tenant_widget_configs_id'), table_name='tenant_widget_configs')
    op.drop_table('tenant_widget_configs')
