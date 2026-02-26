"""add pipeline_stage to leads

Revision ID: 894af05a3c74
Revises: db46ad70483a
Create Date: 2026-02-26 15:05:32.374792

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '894af05a3c74'
down_revision: Union[str, None] = 'db46ad70483a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('pipeline_stage', sa.String(50), nullable=True, server_default='new_lead'))
    op.create_index(op.f('ix_leads_pipeline_stage'), 'leads', ['pipeline_stage'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_leads_pipeline_stage'), table_name='leads')
    op.drop_column('leads', 'pipeline_stage')
