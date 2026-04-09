"""add owner_phone to tenant_business_profiles

Revision ID: a1fea067b2e2
Revises: add_lead_tasks
Create Date: 2026-04-08 19:21:47.577867

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1fea067b2e2'
down_revision: Union[str, None] = 'add_lead_tasks'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenant_business_profiles', sa.Column('owner_phone', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('tenant_business_profiles', 'owner_phone')
