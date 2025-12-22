"""merge contact branches

Revision ID: 19873b8cba02
Revises: add_contact_merge_delete, add_lead_id_to_contacts
Create Date: 2025-12-21 17:14:24.135243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '19873b8cba02'
down_revision: Union[str, None] = ('add_contact_merge_delete', 'add_lead_id_to_contacts')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

