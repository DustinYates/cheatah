"""merge_widget_api_key_and_contact_id

Revision ID: 4f5fc47de1ee
Revises: add_contact_id_to_leads, add_widget_api_key
Create Date: 2026-01-23 16:39:40.159108

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f5fc47de1ee'
down_revision: Union[str, None] = ('add_contact_id_to_leads', 'add_widget_api_key')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

