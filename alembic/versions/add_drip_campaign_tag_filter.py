"""Add audience_filter, tag_filter, priority to drip_campaigns and drop type unique constraint

Revision ID: add_drip_tag_filter
Revises: add_google_ads_key
Create Date: 2026-04-25

Allows tenants to define multiple drip campaigns per tenant, routed by
audience and lead tags rather than a hardcoded kids/adults pair. The
existing kids/adults campaigns are backfilled into the new schema so
behavior is unchanged on day 1.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'add_drip_tag_filter'
down_revision: Union[str, None] = 'add_google_ads_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'drip_campaigns',
        sa.Column('audience_filter', sa.String(length=50), nullable=True),
    )
    op.add_column(
        'drip_campaigns',
        sa.Column('tag_filter', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'drip_campaigns',
        sa.Column('priority', sa.Integer(), nullable=False, server_default='100'),
    )

    # Backfill existing kids/adults campaigns into the new schema
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE drip_campaigns SET audience_filter = 'child' WHERE campaign_type = 'kids' AND audience_filter IS NULL"
    ))
    conn.execute(sa.text(
        "UPDATE drip_campaigns SET audience_filter = 'adult' WHERE campaign_type = 'adults' AND audience_filter IS NULL"
    ))

    # Drop the legacy unique constraint so a tenant can have multiple campaigns
    op.drop_constraint('uq_drip_campaign_tenant_type', 'drip_campaigns', type_='unique')


def downgrade() -> None:
    op.create_unique_constraint(
        'uq_drip_campaign_tenant_type',
        'drip_campaigns',
        ['tenant_id', 'campaign_type'],
    )
    op.drop_column('drip_campaigns', 'priority')
    op.drop_column('drip_campaigns', 'tag_filter')
    op.drop_column('drip_campaigns', 'audience_filter')
