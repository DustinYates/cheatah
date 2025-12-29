"""Add tenant_number field for admin-assignable IDs.

Revision ID: add_tenant_number
Revises: add_lead_id_to_contacts
Create Date: 2025-01-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_tenant_number'
down_revision = 'add_lead_id_to_contacts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('tenant_number', sa.String(50), nullable=True))
    op.create_index('ix_tenants_tenant_number', 'tenants', ['tenant_number'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_tenants_tenant_number', table_name='tenants')
    op.drop_column('tenants', 'tenant_number')
