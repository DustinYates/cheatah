"""add_sms_models

Revision ID: add_sms_models
Revises: 3757de506b23
Create Date: 2025-01-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_sms_models'
down_revision: Union[str, None] = '3757de506b23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add phone_number to conversations
    op.add_column('conversations', sa.Column('phone_number', sa.String(length=50), nullable=True))
    op.create_index(op.f('ix_conversations_phone_number'), 'conversations', ['phone_number'], unique=False)
    
    # Add metadata to messages
    op.add_column('messages', sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    
    # Create tenant_sms_configs table
    op.create_table('tenant_sms_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('twilio_account_sid', sa.String(length=255), nullable=True),
        sa.Column('twilio_auth_token', sa.String(length=255), nullable=True),
        sa.Column('twilio_phone_number', sa.String(length=50), nullable=True),
        sa.Column('business_hours_enabled', sa.Boolean(), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('business_hours', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('auto_reply_outside_hours', sa.Boolean(), nullable=False),
        sa.Column('auto_reply_message', sa.Text(), nullable=True),
        sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index(op.f('ix_tenant_sms_configs_id'), 'tenant_sms_configs', ['id'], unique=False)
    op.create_index(op.f('ix_tenant_sms_configs_tenant_id'), 'tenant_sms_configs', ['tenant_id'], unique=True)
    
    # Create sms_opt_ins table
    op.create_table('sms_opt_ins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('phone_number', sa.String(length=50), nullable=False),
        sa.Column('is_opted_in', sa.Boolean(), nullable=False),
        sa.Column('opted_in_at', sa.DateTime(), nullable=True),
        sa.Column('opted_out_at', sa.DateTime(), nullable=True),
        sa.Column('opt_in_method', sa.String(length=50), nullable=True),
        sa.Column('opt_out_method', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sms_opt_ins_id'), 'sms_opt_ins', ['id'], unique=False)
    op.create_index(op.f('ix_sms_opt_ins_tenant_id'), 'sms_opt_ins', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_sms_opt_ins_phone_number'), 'sms_opt_ins', ['phone_number'], unique=False)
    
    # Create escalations table
    op.create_table('escalations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('confidence_score', sa.String(length=50), nullable=True),
        sa.Column('trigger_message', sa.Text(), nullable=True),
        sa.Column('admin_notified_at', sa.DateTime(), nullable=True),
        sa.Column('notification_methods', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('notification_status', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_escalations_id'), 'escalations', ['id'], unique=False)
    op.create_index(op.f('ix_escalations_tenant_id'), 'escalations', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_escalations_conversation_id'), 'escalations', ['conversation_id'], unique=False)


def downgrade() -> None:
    # Drop escalations table
    op.drop_index(op.f('ix_escalations_conversation_id'), table_name='escalations')
    op.drop_index(op.f('ix_escalations_tenant_id'), table_name='escalations')
    op.drop_index(op.f('ix_escalations_id'), table_name='escalations')
    op.drop_table('escalations')
    
    # Drop sms_opt_ins table
    op.drop_index(op.f('ix_sms_opt_ins_phone_number'), table_name='sms_opt_ins')
    op.drop_index(op.f('ix_sms_opt_ins_tenant_id'), table_name='sms_opt_ins')
    op.drop_index(op.f('ix_sms_opt_ins_id'), table_name='sms_opt_ins')
    op.drop_table('sms_opt_ins')
    
    # Drop tenant_sms_configs table
    op.drop_index(op.f('ix_tenant_sms_configs_tenant_id'), table_name='tenant_sms_configs')
    op.drop_index(op.f('ix_tenant_sms_configs_id'), table_name='tenant_sms_configs')
    op.drop_table('tenant_sms_configs')
    
    # Remove metadata from messages
    op.drop_column('messages', 'metadata')
    
    # Remove phone_number from conversations
    op.drop_index(op.f('ix_conversations_phone_number'), table_name='conversations')
    op.drop_column('conversations', 'phone_number')

