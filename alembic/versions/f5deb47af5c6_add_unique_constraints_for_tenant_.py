"""add_unique_constraints_for_tenant_prompt_isolation

Revision ID: f5deb47af5c6
Revises: add_tenant_business_profile
Create Date: 2025-12-13 18:09:34.975139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5deb47af5c6'
down_revision: Union[str, None] = 'add_tenant_business_profile'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraints to ensure proper tenant data isolation."""
    # Ensure each tenant can only have one prompt bundle with a given name and version
    # This allows tenants to have "Customer Service v1.0" without conflicting with other tenants
    op.create_unique_constraint(
        'uq_prompt_bundles_tenant_name_version',
        'prompt_bundles',
        ['tenant_id', 'name', 'version']
    )

    # Ensure each tenant can only have one PRODUCTION bundle at a time
    # Global (tenant_id=NULL) can also only have one production bundle
    op.create_index(
        'uq_prompt_bundles_tenant_production',
        'prompt_bundles',
        ['tenant_id', 'status'],
        unique=True,
        postgresql_where=sa.text("status = 'production'")
    )


def downgrade() -> None:
    """Remove unique constraints."""
    op.drop_index('uq_prompt_bundles_tenant_production', table_name='prompt_bundles')
    op.drop_constraint('uq_prompt_bundles_tenant_name_version', 'prompt_bundles', type_='unique')

