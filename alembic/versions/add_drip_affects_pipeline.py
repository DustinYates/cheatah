"""Add drip_affects_pipeline to tenant_business_profiles

Revision ID: add_drip_affects_pipeline
Revises: add_lead_score
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_drip_affects_pipeline'
down_revision = 'add_lead_score'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tenant_business_profiles',
        sa.Column(
            'drip_affects_pipeline',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('true'),
        ),
    )


def downgrade() -> None:
    op.drop_column('tenant_business_profiles', 'drip_affects_pipeline')
