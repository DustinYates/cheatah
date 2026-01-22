"""Add SendGrid outbound configuration for per-tenant email sending

Adds sendgrid_api_key and sendgrid_from_email columns to tenant_email_configs
for multi-tenant outbound email support.

Revision ID: add_sendgrid_outbound_config
Revises: add_sendgrid_inbound_parse
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_sendgrid_outbound_config'
down_revision = 'add_sendgrid_inbound_parse'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add SendGrid outbound configuration fields to tenant_email_configs
    op.add_column(
        'tenant_email_configs',
        sa.Column('sendgrid_api_key', sa.String(255), nullable=True)
    )
    op.add_column(
        'tenant_email_configs',
        sa.Column('sendgrid_from_email', sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('tenant_email_configs', 'sendgrid_from_email')
    op.drop_column('tenant_email_configs', 'sendgrid_api_key')
