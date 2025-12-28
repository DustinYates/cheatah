"""Add Telnyx provider fields to tenant_sms_configs

Revision ID: add_telnyx_provider_fields
Revises: add_user_contact_link
Create Date: 2025-12-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_telnyx_provider_fields'
down_revision = 'add_user_contact_link'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add provider column (defaults to 'twilio' for existing records)
    op.add_column(
        'tenant_sms_configs',
        sa.Column('provider', sa.String(length=20), nullable=False, server_default='twilio')
    )

    # Add Telnyx configuration columns
    op.add_column(
        'tenant_sms_configs',
        sa.Column('telnyx_api_key', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'tenant_sms_configs',
        sa.Column('telnyx_messaging_profile_id', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'tenant_sms_configs',
        sa.Column('telnyx_connection_id', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'tenant_sms_configs',
        sa.Column('telnyx_phone_number', sa.String(length=50), nullable=True)
    )

    # Add voice configuration columns
    op.add_column(
        'tenant_sms_configs',
        sa.Column('voice_phone_number', sa.String(length=50), nullable=True)
    )
    op.add_column(
        'tenant_sms_configs',
        sa.Column('voice_enabled', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    # Remove voice configuration columns
    op.drop_column('tenant_sms_configs', 'voice_enabled')
    op.drop_column('tenant_sms_configs', 'voice_phone_number')

    # Remove Telnyx configuration columns
    op.drop_column('tenant_sms_configs', 'telnyx_phone_number')
    op.drop_column('tenant_sms_configs', 'telnyx_connection_id')
    op.drop_column('tenant_sms_configs', 'telnyx_messaging_profile_id')
    op.drop_column('tenant_sms_configs', 'telnyx_api_key')

    # Remove provider column
    op.drop_column('tenant_sms_configs', 'provider')
