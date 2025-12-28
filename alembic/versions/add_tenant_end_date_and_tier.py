"""Add end_date and tier to tenants

Revision ID: add_tenant_end_date_and_tier
Revises: add_telnyx_provider_fields
Create Date: 2025-12-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_tenant_end_date_and_tier"
down_revision = "add_telnyx_provider_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("tenants", sa.Column("tier", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "tier")
    op.drop_column("tenants", "end_date")
