"""Add do_not_contact table for DNC opt-out management

Revision ID: add_do_not_contact
Revises: encrypt_sensitive_credentials
Create Date: 2026-01-22

This table tracks phone numbers and emails that have requested
not to be contacted. This includes both automated detection
(e.g., "don't contact me" messages) and manual flagging.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_do_not_contact'
down_revision = 'encrypt_sensitive_credentials'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create do_not_contact table."""
    op.create_table(
        'do_not_contact',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('phone_number', sa.String(length=50), nullable=True, index=True),
        sa.Column('email', sa.String(length=255), nullable=True, index=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('source_channel', sa.String(length=50), nullable=False),
        sa.Column('source_message', sa.Text(), nullable=True),
        sa.Column('source_conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('deactivated_at', sa.DateTime(), nullable=True),
        sa.Column('deactivated_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('deactivation_reason', sa.String(length=255), nullable=True),
        sa.CheckConstraint(
            'phone_number IS NOT NULL OR email IS NOT NULL',
            name='chk_dnc_has_identifier'
        ),
    )

    # Composite indexes for fast lookups
    op.create_index('idx_dnc_tenant_phone_active', 'do_not_contact', ['tenant_id', 'phone_number', 'is_active'])
    op.create_index('idx_dnc_tenant_email_active', 'do_not_contact', ['tenant_id', 'email', 'is_active'])


def downgrade() -> None:
    """Remove do_not_contact table."""
    op.drop_index('idx_dnc_tenant_email_active')
    op.drop_index('idx_dnc_tenant_phone_active')
    op.drop_table('do_not_contact')
