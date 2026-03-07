"""Add Outlook email integration columns

Revision ID: add_outlook_email_columns
Revises: remove_twilio_columns
Create Date: 2026-03-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_outlook_email_columns'
down_revision = 'remove_twilio_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Outlook OAuth credentials on tenant_email_configs
    op.add_column('tenant_email_configs', sa.Column('outlook_email', sa.String(255), nullable=True))
    op.add_column('tenant_email_configs', sa.Column('outlook_refresh_token', sa.Text(), nullable=True))
    op.add_column('tenant_email_configs', sa.Column('outlook_access_token', sa.Text(), nullable=True))
    op.add_column('tenant_email_configs', sa.Column('outlook_token_expires_at', sa.DateTime(), nullable=True))
    op.add_column('tenant_email_configs', sa.Column('outlook_subscription_id', sa.String(255), nullable=True))
    op.add_column('tenant_email_configs', sa.Column('outlook_subscription_expiration', sa.DateTime(), nullable=True))
    op.add_column('tenant_email_configs', sa.Column('outlook_client_state', sa.String(512), nullable=True))

    # Outlook conversation ID on email_conversations
    op.add_column('email_conversations', sa.Column('outlook_conversation_id', sa.String(255), nullable=True))
    op.create_index('ix_email_conversations_outlook_conversation_id', 'email_conversations', ['outlook_conversation_id'])

    # Make gmail_thread_id nullable (Outlook emails won't have one)
    op.alter_column('email_conversations', 'gmail_thread_id', existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    op.alter_column('email_conversations', 'gmail_thread_id', existing_type=sa.String(255), nullable=False)
    op.drop_index('ix_email_conversations_outlook_conversation_id', 'email_conversations')
    op.drop_column('email_conversations', 'outlook_conversation_id')
    op.drop_column('tenant_email_configs', 'outlook_client_state')
    op.drop_column('tenant_email_configs', 'outlook_subscription_expiration')
    op.drop_column('tenant_email_configs', 'outlook_subscription_id')
    op.drop_column('tenant_email_configs', 'outlook_token_expires_at')
    op.drop_column('tenant_email_configs', 'outlook_access_token')
    op.drop_column('tenant_email_configs', 'outlook_refresh_token')
    op.drop_column('tenant_email_configs', 'outlook_email')
