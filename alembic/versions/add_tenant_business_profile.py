"""Add tenant business profile table

Revision ID: add_tenant_business_profile
Revises: 0e0a47c4ec9a
Create Date: 2024-12-13

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_tenant_business_profile'
down_revision = '0e0a47c4ec9a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tenant_business_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('business_name', sa.String(255), nullable=True),
        sa.Column('website_url', sa.Text(), nullable=True),
        sa.Column('phone_number', sa.String(50), nullable=True),
        sa.Column('twilio_phone', sa.String(50), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('profile_complete', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id')
    )
    op.create_index('ix_tenant_business_profiles_id', 'tenant_business_profiles', ['id'])
    op.create_index('ix_tenant_business_profiles_tenant_id', 'tenant_business_profiles', ['tenant_id'])
    
    op.execute("""
        INSERT INTO tenant_business_profiles (tenant_id, profile_complete, created_at, updated_at)
        SELECT id, false, NOW(), NOW() FROM tenants
        WHERE id NOT IN (SELECT tenant_id FROM tenant_business_profiles)
    """)


def downgrade() -> None:
    op.drop_index('ix_tenant_business_profiles_tenant_id', 'tenant_business_profiles')
    op.drop_index('ix_tenant_business_profiles_id', 'tenant_business_profiles')
    op.drop_table('tenant_business_profiles')
