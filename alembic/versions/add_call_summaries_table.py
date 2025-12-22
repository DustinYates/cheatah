"""add call_summaries table

Revision ID: add_call_summaries
Revises: add_calls_voice_phone
Create Date: 2025-12-22 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_call_summaries'
down_revision: Union[str, None] = 'add_calls_voice_phone'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create call_summaries table
    op.create_table(
        'call_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('call_id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=True),
        sa.Column('lead_id', sa.Integer(), nullable=True),
        sa.Column('intent', sa.String(length=50), nullable=True),
        sa.Column('outcome', sa.String(length=50), nullable=True),
        sa.Column('summary_text', sa.Text(), nullable=True),
        sa.Column('extracted_fields', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['call_id'], ['calls.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_call_summaries_id', 'call_summaries', ['id'], unique=False)
    op.create_index('ix_call_summaries_call_id', 'call_summaries', ['call_id'], unique=True)
    op.create_index('ix_call_summaries_contact_id', 'call_summaries', ['contact_id'], unique=False)
    op.create_index('ix_call_summaries_lead_id', 'call_summaries', ['lead_id'], unique=False)
    op.create_index('ix_call_summaries_intent', 'call_summaries', ['intent'], unique=False)
    op.create_index('ix_call_summaries_outcome', 'call_summaries', ['outcome'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_call_summaries_outcome', 'call_summaries')
    op.drop_index('ix_call_summaries_intent', 'call_summaries')
    op.drop_index('ix_call_summaries_lead_id', 'call_summaries')
    op.drop_index('ix_call_summaries_contact_id', 'call_summaries')
    op.drop_index('ix_call_summaries_call_id', 'call_summaries')
    op.drop_index('ix_call_summaries_id', 'call_summaries')
    op.drop_table('call_summaries')

