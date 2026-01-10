"""Add fallback_voice_prompt to tenant_voice_configs

Revision ID: add_fallback_voice_prompt
Revises: add_scraped_profile_fields
Create Date: 2026-01-09

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_fallback_voice_prompt'
down_revision = 'add_scraped_profile_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tenant_voice_configs', sa.Column('fallback_voice_prompt', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tenant_voice_configs', 'fallback_voice_prompt')
