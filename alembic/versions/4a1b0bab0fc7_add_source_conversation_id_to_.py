"""add_source_conversation_id_to_conversations

Revision ID: 4a1b0bab0fc7
Revises: add_conversation_topic
Create Date: 2026-02-02 19:31:30.251645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4a1b0bab0fc7'
down_revision: Union[str, None] = 'add_conversation_topic'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('source_conversation_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_conversations_source_conversation_id'), 'conversations', ['source_conversation_id'], unique=False)
    op.create_foreign_key('fk_conversations_source_conversation_id', 'conversations', 'conversations', ['source_conversation_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_conversations_source_conversation_id', 'conversations', type_='foreignkey')
    op.drop_index(op.f('ix_conversations_source_conversation_id'), table_name='conversations')
    op.drop_column('conversations', 'source_conversation_id')
