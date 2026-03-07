"""Remove Twilio columns and rename business profile phone columns

Revision ID: remove_twilio_columns
Revises: f7e8d9c0b1a2
Create Date: 2026-03-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'remove_twilio_columns'
down_revision = 'f7e8d9c0b1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop Twilio columns from tenant_sms_configs
    op.drop_column('tenant_sms_configs', 'twilio_account_sid')
    op.drop_column('tenant_sms_configs', 'twilio_auth_token')
    op.drop_column('tenant_sms_configs', 'twilio_phone_number')

    # Update provider default from 'twilio' to 'telnyx'
    op.alter_column(
        'tenant_sms_configs',
        'provider',
        server_default='telnyx',
    )
    # Update any existing rows still set to 'twilio'
    op.execute("UPDATE tenant_sms_configs SET provider = 'telnyx' WHERE provider = 'twilio'")

    # Rename business profile phone columns
    op.alter_column('tenant_business_profiles', 'twilio_phone', new_column_name='sms_phone')
    op.alter_column('tenant_business_profiles', 'twilio_voice_phone', new_column_name='voice_phone')


def downgrade() -> None:
    # Restore business profile column names
    op.alter_column('tenant_business_profiles', 'sms_phone', new_column_name='twilio_phone')
    op.alter_column('tenant_business_profiles', 'voice_phone', new_column_name='twilio_voice_phone')

    # Restore provider default
    op.alter_column(
        'tenant_sms_configs',
        'provider',
        server_default='twilio',
    )

    # Re-add Twilio columns
    op.add_column('tenant_sms_configs', sa.Column('twilio_phone_number', sa.String(50), nullable=True))
    op.add_column('tenant_sms_configs', sa.Column('twilio_auth_token', sa.String(255), nullable=True))
    op.add_column('tenant_sms_configs', sa.Column('twilio_account_sid', sa.String(255), nullable=True))
