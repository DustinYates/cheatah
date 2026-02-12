"""add_must_change_password_to_users

Revision ID: 27e99ad1ae35
Revises: 373dd7474501
Create Date: 2026-02-12 14:36:03.019278

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '27e99ad1ae35'
down_revision: Union[str, None] = '373dd7474501'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')

