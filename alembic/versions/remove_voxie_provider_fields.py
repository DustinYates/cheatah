"""Remove Voxie provider fields from tenant_sms_configs

Voxie integration is being removed from the application.
This migration drops the voxie_api_key, voxie_team_id, and voxie_phone_number columns.

Revision ID: remove_voxie_provider_fields
Revises: add_sendgrid_outbound_config
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa


revision = 'remove_voxie_provider_fields'
down_revision = 'add_sendgrid_outbound_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop Voxie provider columns from tenant_sms_configs
    op.drop_column('tenant_sms_configs', 'voxie_phone_number')
    op.drop_column('tenant_sms_configs', 'voxie_team_id')
    op.drop_column('tenant_sms_configs', 'voxie_api_key')


def downgrade() -> None:
    # Re-add Voxie provider columns (in case of rollback)
    op.add_column('tenant_sms_configs', sa.Column('voxie_api_key', sa.String(255), nullable=True))
    op.add_column('tenant_sms_configs', sa.Column('voxie_team_id', sa.String(50), nullable=True))
    op.add_column('tenant_sms_configs', sa.Column('voxie_phone_number', sa.String(50), nullable=True))
