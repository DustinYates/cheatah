"""Add channel field to prompt_bundles for voice/sms/chat separation

Revision ID: add_prompt_channel
Revises: add_fallback_voice_prompt
Create Date: 2026-01-09

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_prompt_channel'
down_revision = 'add_voxie_provider_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add channel column with default 'chat' for existing records
    op.add_column('prompt_bundles', sa.Column('channel', sa.String(20), nullable=False, server_default='chat'))

    # Add index on channel for faster lookups
    op.create_index('ix_prompt_bundles_channel', 'prompt_bundles', ['channel'])

    # Drop old unique constraint (if exists) and create new one including channel
    # Note: The old constraint may not exist in all environments
    try:
        op.drop_constraint('uq_prompt_bundles_tenant_name_version', 'prompt_bundles', type_='unique')
    except Exception:
        pass  # Constraint may not exist

    op.create_unique_constraint(
        'uq_prompt_bundles_tenant_name_version_channel',
        'prompt_bundles',
        ['tenant_id', 'name', 'version', 'channel']
    )

    # Drop old production unique index and create new one including channel
    try:
        op.drop_index('uq_prompt_bundles_tenant_production', 'prompt_bundles')
    except Exception:
        pass  # Index may not exist

    # Create new partial unique index for production bundles per channel
    # PostgreSQL-specific: ensures only one production bundle per tenant per channel
    op.execute("""
        CREATE UNIQUE INDEX uq_prompt_bundles_tenant_channel_production
        ON prompt_bundles (tenant_id, channel, status)
        WHERE status = 'production'
    """)


def downgrade() -> None:
    # Drop new index
    op.drop_index('uq_prompt_bundles_tenant_channel_production', 'prompt_bundles')

    # Drop new constraint
    op.drop_constraint('uq_prompt_bundles_tenant_name_version_channel', 'prompt_bundles', type_='unique')

    # Recreate old constraint
    op.create_unique_constraint(
        'uq_prompt_bundles_tenant_name_version',
        'prompt_bundles',
        ['tenant_id', 'name', 'version']
    )

    # Recreate old production index
    op.execute("""
        CREATE UNIQUE INDEX uq_prompt_bundles_tenant_production
        ON prompt_bundles (tenant_id, status)
        WHERE status = 'production'
    """)

    # Drop channel index and column
    op.drop_index('ix_prompt_bundles_channel', 'prompt_bundles')
    op.drop_column('prompt_bundles', 'channel')
