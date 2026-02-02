"""Add topic column to conversations table for topic analytics

Revision ID: add_conversation_topic
Revises: add_admin_dashboard_tables
Create Date: 2026-02-01

Adds:
- conversations.topic: keyword-classified topic for analytics histogram
- Backfills voice conversations from call_summaries.intent
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_conversation_topic'
down_revision = 'add_admin_dashboard_tables'
branch_labels = None
depends_on = None


# Mapping from CallSummary.intent to unified topic taxonomy
INTENT_TO_TOPIC = {
    'pricing_info': 'pricing',
    'booking_request': 'scheduling',
    'hours_location': 'hours_location',
    'support_request': 'support_request',
    'wrong_number': 'wrong_number',
    'general_inquiry': 'general_inquiry',
}


def upgrade() -> None:
    op.add_column('conversations', sa.Column('topic', sa.String(50), nullable=True))
    op.create_index('ix_conversations_topic', 'conversations', ['topic'])

    # Backfill voice conversations from call_summaries.intent
    # Join conversations (channel='voice') to calls via phone_number + tenant_id,
    # then to call_summaries for the intent value.
    for old_intent, new_topic in INTENT_TO_TOPIC.items():
        op.execute(
            sa.text(
                """
                UPDATE conversations c
                SET topic = :new_topic
                FROM calls ca
                JOIN call_summaries cs ON cs.call_id = ca.id
                WHERE c.channel = 'voice'
                  AND c.topic IS NULL
                  AND ca.tenant_id = c.tenant_id
                  AND ca.from_number = c.phone_number
                  AND cs.intent = :old_intent
                  AND ca.created_at >= c.created_at - interval '5 minutes'
                  AND ca.created_at <= c.created_at + interval '30 minutes'
                """
            ).bindparams(new_topic=new_topic, old_intent=old_intent)
        )


def downgrade() -> None:
    op.drop_index('ix_conversations_topic', table_name='conversations')
    op.drop_column('conversations', 'topic')
