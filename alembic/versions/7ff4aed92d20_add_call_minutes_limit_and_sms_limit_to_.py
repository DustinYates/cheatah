"""add_call_minutes_limit_and_sms_limit_to_tenants

Revision ID: 7ff4aed92d20
Revises: 76a30dae7698
Create Date: 2026-02-11 06:01:59.148288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7ff4aed92d20'
down_revision: Union[str, None] = '76a30dae7698'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('call_minutes_limit', sa.Integer(), nullable=True))
    op.add_column('tenants', sa.Column('sms_limit', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'sms_limit')
    op.drop_column('tenants', 'call_minutes_limit')
