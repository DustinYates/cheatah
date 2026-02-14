"""add_voice_agent_id_to_voice_configs

Revision ID: db46ad70483a
Revises: a1b2c3d4e5f6
Create Date: 2026-02-14 08:27:25.632296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'db46ad70483a'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add voice_agent_id column for second Telnyx AI agent per tenant
    op.add_column(
        'tenant_voice_configs',
        sa.Column('voice_agent_id', sa.String(255), nullable=True),
    )

    # Populate tenant 3 (BSS Cypress-Spring) with second agent
    op.execute(
        "UPDATE tenant_voice_configs "
        "SET voice_agent_id = 'assistant-5cf97080-b297-42d5-a2e3-7ac43b32d6c5' "
        "WHERE tenant_id = 3"
    )

    # Set tenant 3's second phone number
    op.execute(
        "UPDATE tenant_sms_configs "
        "SET voice_phone_number = '+12816260873' "
        "WHERE tenant_id = 3"
    )


def downgrade() -> None:
    # Clear tenant 3 voice_phone_number
    op.execute(
        "UPDATE tenant_sms_configs "
        "SET voice_phone_number = NULL "
        "WHERE tenant_id = 3"
    )

    op.drop_column('tenant_voice_configs', 'voice_agent_id')
