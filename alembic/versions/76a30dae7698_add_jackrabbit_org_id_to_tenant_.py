"""add jackrabbit_org_id to tenant_customer_service_configs

Revision ID: 76a30dae7698
Revises: add_forum_comments
Create Date: 2026-02-10 22:20:04.040708

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '76a30dae7698'
down_revision: Union[str, None] = 'add_forum_comments'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenant_customer_service_configs',
        sa.Column('jackrabbit_org_id', sa.String(length=50), nullable=True),
    )
    # Seed known tenants
    op.execute(
        "UPDATE tenant_customer_service_configs SET jackrabbit_org_id = '545911' WHERE tenant_id = 3"
    )
    op.execute(
        "UPDATE tenant_customer_service_configs SET jackrabbit_org_id = '526069' WHERE tenant_id = 237"
    )


def downgrade() -> None:
    op.drop_column('tenant_customer_service_configs', 'jackrabbit_org_id')
