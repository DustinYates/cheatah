"""Add scraped profile fields for website scraping

Revision ID: add_scraped_profile_fields
Revises: 15a8a4c29c8f
Create Date: 2026-01-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_scraped_profile_fields'
down_revision = '15a8a4c29c8f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add scraped data columns to tenant_business_profiles
    op.add_column('tenant_business_profiles', sa.Column('scraped_services', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_hours', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_locations', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_pricing', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_faqs', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_policies', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_programs', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_unique_selling_points', sa.JSON(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_target_audience', sa.Text(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('scraped_raw_content', sa.Text(), nullable=True))
    op.add_column('tenant_business_profiles', sa.Column('last_scraped_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('tenant_business_profiles', 'last_scraped_at')
    op.drop_column('tenant_business_profiles', 'scraped_raw_content')
    op.drop_column('tenant_business_profiles', 'scraped_target_audience')
    op.drop_column('tenant_business_profiles', 'scraped_unique_selling_points')
    op.drop_column('tenant_business_profiles', 'scraped_programs')
    op.drop_column('tenant_business_profiles', 'scraped_policies')
    op.drop_column('tenant_business_profiles', 'scraped_faqs')
    op.drop_column('tenant_business_profiles', 'scraped_pricing')
    op.drop_column('tenant_business_profiles', 'scraped_locations')
    op.drop_column('tenant_business_profiles', 'scraped_hours')
    op.drop_column('tenant_business_profiles', 'scraped_services')
