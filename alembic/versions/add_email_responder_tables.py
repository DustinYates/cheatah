"""Add email responder tables

Revision ID: add_email_responder
Revises: add_phase2_voice_handoff
Create Date: 2024-12-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_email_responder'
down_revision = 'add_phase2_voice_handoff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tenant_email_configs table
    op.create_table(
        'tenant_email_configs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, unique=True, index=True),
        sa.Column('is_enabled', sa.Boolean(), default=False, nullable=False),
        
        # Gmail OAuth
        sa.Column('gmail_email', sa.String(length=255), nullable=True),
        sa.Column('gmail_refresh_token', sa.Text(), nullable=True),
        sa.Column('gmail_access_token', sa.Text(), nullable=True),
        sa.Column('gmail_token_expires_at', sa.DateTime(), nullable=True),
        
        # Gmail API sync
        sa.Column('last_history_id', sa.String(length=100), nullable=True),
        sa.Column('watch_expiration', sa.DateTime(), nullable=True),
        
        # Business hours
        sa.Column('business_hours_enabled', sa.Boolean(), default=False, nullable=False),
        sa.Column('auto_reply_outside_hours', sa.Boolean(), default=True, nullable=False),
        sa.Column('auto_reply_message', sa.Text(), nullable=True),
        
        # Response settings
        sa.Column('response_signature', sa.Text(), nullable=True),
        sa.Column('max_thread_depth', sa.Integer(), default=10),
        
        # Notification and escalation
        sa.Column('notification_methods', sa.JSON(), nullable=True),
        sa.Column('escalation_rules', sa.JSON(), nullable=True),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create email_conversations table
    op.create_table(
        'email_conversations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id'), nullable=True, index=True),
        
        # Gmail identifiers
        sa.Column('gmail_thread_id', sa.String(length=255), nullable=False, index=True),
        sa.Column('gmail_message_id', sa.String(length=255), nullable=True),
        
        # Email metadata
        sa.Column('subject', sa.String(length=500), nullable=True),
        sa.Column('from_email', sa.String(length=255), nullable=False, index=True),
        sa.Column('to_email', sa.String(length=255), nullable=False),
        
        # Status tracking
        sa.Column('status', sa.String(length=50), default='active', nullable=False),
        sa.Column('last_response_at', sa.DateTime(), nullable=True),
        sa.Column('message_count', sa.Integer(), default=1, nullable=False),
        
        # Lead/contact linkage
        sa.Column('contact_id', sa.Integer(), sa.ForeignKey('contacts.id'), nullable=True, index=True),
        sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=True, index=True),
        
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create unique constraint for tenant + thread_id
    op.create_unique_constraint(
        'uq_email_conversations_tenant_thread',
        'email_conversations',
        ['tenant_id', 'gmail_thread_id']
    )


def downgrade() -> None:
    # Drop email_conversations table
    op.drop_constraint('uq_email_conversations_tenant_thread', 'email_conversations', type_='unique')
    op.drop_table('email_conversations')
    
    # Drop tenant_email_configs table
    op.drop_table('tenant_email_configs')

