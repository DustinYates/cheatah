"""Add widget_api_key to tenant_widget_configs for public chat endpoint security

Revision ID: add_widget_api_key
Revises: add_do_not_contact
Create Date: 2026-01-23

Adds an API key field to tenant_widget_configs that must be passed
when calling the public chat endpoint. This prevents unauthorized
access to tenant chatbots by requiring a secret key.
"""
from alembic import op
import sqlalchemy as sa
import secrets

revision = 'add_widget_api_key'
down_revision = 'add_do_not_contact'
branch_labels = None
depends_on = None


def generate_api_key() -> str:
    """Generate a secure API key (32 bytes = 64 hex chars)."""
    return secrets.token_hex(32)


def upgrade() -> None:
    """Add widget_api_key column and generate keys for existing configs."""
    # Add column (nullable initially)
    op.add_column(
        'tenant_widget_configs',
        sa.Column('widget_api_key', sa.String(length=64), nullable=True, unique=True)
    )

    # Create index for fast lookups
    op.create_index(
        'ix_tenant_widget_configs_api_key',
        'tenant_widget_configs',
        ['widget_api_key'],
        unique=True
    )

    # Generate API keys for existing configs
    connection = op.get_bind()
    result = connection.execute(sa.text("SELECT id FROM tenant_widget_configs WHERE widget_api_key IS NULL"))

    for row in result:
        api_key = generate_api_key()
        connection.execute(
            sa.text("UPDATE tenant_widget_configs SET widget_api_key = :key WHERE id = :id"),
            {"key": api_key, "id": row.id}
        )

    # Also create widget configs for tenants that don't have one yet
    orphan_tenants = connection.execute(
        sa.text("""
            SELECT t.id FROM tenants t
            LEFT JOIN tenant_widget_configs twc ON t.id = twc.tenant_id
            WHERE twc.id IS NULL
        """)
    )

    for row in orphan_tenants:
        api_key = generate_api_key()
        connection.execute(
            sa.text("""
                INSERT INTO tenant_widget_configs (tenant_id, widget_api_key, created_at, updated_at)
                VALUES (:tenant_id, :api_key, NOW(), NOW())
            """),
            {"tenant_id": row.id, "api_key": api_key}
        )


def downgrade() -> None:
    """Remove widget_api_key column."""
    op.drop_index('ix_tenant_widget_configs_api_key', table_name='tenant_widget_configs')
    op.drop_column('tenant_widget_configs', 'widget_api_key')
