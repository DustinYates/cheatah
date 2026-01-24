"""Add sent_assets table for deduplication

Revision ID: add_sent_assets_table
Revises: auto_convert_existing_leads
Create Date: 2026-01-24

This table provides database-level deduplication for sent assets (registration links,
pricing info, etc.) to prevent duplicate sends even when Redis is unavailable.
The unique constraint ensures atomicity at the database level.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_sent_assets_table'
down_revision = 'auto_convert_existing_leads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sent_assets',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.BigInteger(), nullable=False),
        sa.Column('phone_normalized', sa.String(length=20), nullable=False, comment='Last 10 digits of phone'),
        sa.Column('asset_type', sa.String(length=50), nullable=False, comment='e.g., registration_link, pricing'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('message_id', sa.String(length=100), nullable=True, comment='Provider message ID for audit'),
        sa.Column('conversation_id', sa.BigInteger(), nullable=True, comment='Conversation that triggered the send'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'phone_normalized', 'asset_type', name='uq_sent_assets_tenant_phone_asset'),
    )
    op.create_index('ix_sent_assets_tenant_id', 'sent_assets', ['tenant_id'], unique=False)
    op.create_index('ix_sent_assets_phone_normalized', 'sent_assets', ['phone_normalized'], unique=False)
    op.create_index('ix_sent_assets_lookup', 'sent_assets', ['tenant_id', 'phone_normalized', 'asset_type'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_sent_assets_lookup', table_name='sent_assets')
    op.drop_index('ix_sent_assets_phone_normalized', table_name='sent_assets')
    op.drop_index('ix_sent_assets_tenant_id', table_name='sent_assets')
    op.drop_table('sent_assets')
