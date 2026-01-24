"""merge_sent_assets

Revision ID: b97c37dd6ee5
Revises: 4f5fc47de1ee, add_sent_assets_table
Create Date: 2026-01-24 16:20:16.747835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b97c37dd6ee5'
down_revision: Union[str, None] = ('4f5fc47de1ee', 'add_sent_assets_table')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

