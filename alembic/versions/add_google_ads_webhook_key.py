"""add google_ads_webhook_key column to tenant_business_profiles

Revision ID: add_google_ads_key
Revises: add_stripe_billing
Create Date: 2026-04-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_google_ads_key'
down_revision: Union[str, None] = 'add_stripe_billing'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tenant_business_profiles',
        sa.Column('google_ads_webhook_key', sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tenant_business_profiles', 'google_ads_webhook_key')
