"""Add SendGrid Inbound Parse support for email lead ingestion

Adds SendGrid configuration fields to tenant_email_configs and creates
the email_ingestion_logs table for deduplication and audit trail.

Revision ID: add_sendgrid_inbound_parse
Revises: add_widget_settings_snapshot
Create Date: 2026-01-21

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_sendgrid_inbound_parse'
down_revision = 'add_widget_settings_snapshot'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add SendGrid configuration fields to tenant_email_configs
    op.add_column(
        'tenant_email_configs',
        sa.Column('sendgrid_enabled', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column(
        'tenant_email_configs',
        sa.Column('sendgrid_parse_address', sa.String(255), nullable=True)
    )
    op.add_column(
        'tenant_email_configs',
        sa.Column('sendgrid_webhook_secret', sa.String(255), nullable=True)
    )
    op.add_column(
        'tenant_email_configs',
        sa.Column('email_ingestion_method', sa.String(20), nullable=False, server_default='gmail')
    )

    # Create unique index on sendgrid_parse_address for tenant lookup
    op.create_index(
        'ix_tenant_email_configs_sendgrid_parse_address',
        'tenant_email_configs',
        ['sendgrid_parse_address'],
        unique=True
    )

    # Create email_ingestion_logs table for deduplication and audit
    op.create_table(
        'email_ingestion_logs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('message_id', sa.String(255), nullable=False, index=True),
        sa.Column('message_id_hash', sa.String(64), nullable=True, index=True),
        sa.Column('from_email', sa.String(255), nullable=False),
        sa.Column('to_email', sa.String(255), nullable=True),
        sa.Column('subject', sa.String(500), nullable=True),
        sa.Column('received_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('status', sa.String(50), nullable=False, server_default='received', index=True),
        sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=True, index=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('raw_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Create unique constraint for deduplication
    op.create_unique_constraint(
        'uq_ingestion_tenant_message',
        'email_ingestion_logs',
        ['tenant_id', 'message_id']
    )


def downgrade() -> None:
    # Drop email_ingestion_logs table
    op.drop_constraint('uq_ingestion_tenant_message', 'email_ingestion_logs', type_='unique')
    op.drop_table('email_ingestion_logs')

    # Drop SendGrid fields from tenant_email_configs
    op.drop_index('ix_tenant_email_configs_sendgrid_parse_address', 'tenant_email_configs')
    op.drop_column('tenant_email_configs', 'email_ingestion_method')
    op.drop_column('tenant_email_configs', 'sendgrid_webhook_secret')
    op.drop_column('tenant_email_configs', 'sendgrid_parse_address')
    op.drop_column('tenant_email_configs', 'sendgrid_enabled')
