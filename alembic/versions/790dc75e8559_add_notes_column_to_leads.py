"""add_notes_column_to_leads

Revision ID: 790dc75e8559
Revises: 894af05a3c74
Create Date: 2026-02-28 10:35:04.846729

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '790dc75e8559'
down_revision: Union[str, None] = '894af05a3c74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('leads', 'notes')
