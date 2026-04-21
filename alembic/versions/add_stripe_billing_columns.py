"""add stripe billing columns to tenants

Revision ID: add_stripe_billing
Revises: add_lead_custom_tags
Create Date: 2026-04-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_stripe_billing'
down_revision: Union[str, None] = 'add_lead_custom_tags'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('stripe_customer_id', sa.String(length=255), nullable=True))
    op.add_column('tenants', sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True))
    op.add_column('tenants', sa.Column('subscription_status', sa.String(length=50), nullable=True))
    op.add_column('tenants', sa.Column('current_plan_price_id', sa.String(length=255), nullable=True))
    op.add_column('tenants', sa.Column('current_period_end', sa.DateTime(), nullable=True))
    op.create_index('ix_tenants_stripe_customer_id', 'tenants', ['stripe_customer_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_tenants_stripe_customer_id', table_name='tenants')
    op.drop_column('tenants', 'current_period_end')
    op.drop_column('tenants', 'current_plan_price_id')
    op.drop_column('tenants', 'subscription_status')
    op.drop_column('tenants', 'stripe_subscription_id')
    op.drop_column('tenants', 'stripe_customer_id')
