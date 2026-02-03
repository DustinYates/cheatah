"""add_status_to_conversations

Revision ID: 85f97ceebafb
Revises: 4a1b0bab0fc7
Create Date: 2026-02-02 21:12:58.744493

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '85f97ceebafb'
down_revision: Union[str, None] = '4a1b0bab0fc7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('status', sa.String(length=20), nullable=False, server_default='open'))
    op.create_index(op.f('ix_conversations_status'), 'conversations', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_conversations_status'), table_name='conversations')
    op.drop_column('conversations', 'status')
