"""Add Voxie provider fields to tenant_sms_configs

Revision ID: add_voxie_provider_fields
Revises: add_fallback_voice_prompt
Create Date: 2026-01-09

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_voxie_provider_fields'
down_revision = 'add_fallback_voice_prompt'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add Voxie provider columns to tenant_sms_configs
    op.add_column('tenant_sms_configs', sa.Column('voxie_api_key', sa.String(255), nullable=True))
    op.add_column('tenant_sms_configs', sa.Column('voxie_team_id', sa.String(50), nullable=True))
    op.add_column('tenant_sms_configs', sa.Column('voxie_phone_number', sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column('tenant_sms_configs', 'voxie_phone_number')
    op.drop_column('tenant_sms_configs', 'voxie_team_id')
    op.drop_column('tenant_sms_configs', 'voxie_api_key')
