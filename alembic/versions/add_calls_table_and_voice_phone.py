"""add calls table and twilio_voice_phone

Revision ID: add_calls_voice_phone
Revises: 19873b8cba02
Create Date: 2025-12-22 13:11:56

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_calls_voice_phone'
down_revision: Union[str, None] = '19873b8cba02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add twilio_voice_phone to tenant_business_profiles
    op.add_column('tenant_business_profiles', sa.Column('twilio_voice_phone', sa.String(length=50), nullable=True))
    
    # Create calls table
    op.create_table(
        'calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('call_sid', sa.String(length=255), nullable=False),
        sa.Column('from_number', sa.String(length=50), nullable=False),
        sa.Column('to_number', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='initiated'),
        sa.Column('direction', sa.String(length=20), nullable=False, server_default='inbound'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('duration', sa.Integer(), nullable=True),  # Duration in seconds
        sa.Column('recording_sid', sa.String(length=255), nullable=True),
        sa.Column('recording_url', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calls_id', 'calls', ['id'], unique=False)
    op.create_index('ix_calls_tenant_id', 'calls', ['tenant_id'], unique=False)
    op.create_index('ix_calls_call_sid', 'calls', ['call_sid'], unique=True)
    op.create_index('ix_calls_status', 'calls', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_calls_status', 'calls')
    op.drop_index('ix_calls_call_sid', 'calls')
    op.drop_index('ix_calls_tenant_id', 'calls')
    op.drop_index('ix_calls_id', 'calls')
    op.drop_table('calls')
    op.drop_column('tenant_business_profiles', 'twilio_voice_phone')

