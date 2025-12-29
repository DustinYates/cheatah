"""merge_tenant_number

Revision ID: 15a8a4c29c8f
Revises: add_customer_service_tables, add_tenant_number
Create Date: 2025-12-29 15:07:12.358457

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15a8a4c29c8f'
down_revision: Union[str, None] = ('add_customer_service_tables', 'add_tenant_number')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

