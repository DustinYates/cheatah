"""Add auto_enroll_new_leads to tenant_business_profiles

Revision ID: add_auto_enroll_new_leads
Revises: add_drip_tag_filter
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_auto_enroll_new_leads'
down_revision = 'add_drip_tag_filter'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'tenant_business_profiles',
        sa.Column(
            'auto_enroll_new_leads',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )


def downgrade() -> None:
    op.drop_column('tenant_business_profiles', 'auto_enroll_new_leads')
