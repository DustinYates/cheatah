"""Add tenant_calendar_configs table for Google Calendar scheduling

Revision ID: add_tenant_calendar_configs
Revises: add_jackrabbit_api_keys
Create Date: 2026-01-31

Adds per-tenant Google Calendar configuration including OAuth tokens,
calendar selection, booking link fallback, and scheduling preferences.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_tenant_calendar_configs'
down_revision = 'add_jackrabbit_api_keys'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenant_calendar_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('google_email', sa.String(length=255), nullable=True),
        sa.Column('google_refresh_token', sa.Text(), nullable=True),
        sa.Column('google_access_token', sa.Text(), nullable=True),
        sa.Column('google_token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('calendar_id', sa.String(length=255), nullable=True, server_default='primary'),
        sa.Column('booking_link_url', sa.String(length=500), nullable=True),
        sa.Column('scheduling_preferences', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_tenant_calendar_configs_id'), 'tenant_calendar_configs', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_calendar_configs_tenant_id'), 'tenant_calendar_configs', ['tenant_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_tenant_calendar_configs_tenant_id'), table_name='tenant_calendar_configs')
    op.drop_index(op.f('ix_tenant_calendar_configs_id'), table_name='tenant_calendar_configs')
    op.drop_table('tenant_calendar_configs')
