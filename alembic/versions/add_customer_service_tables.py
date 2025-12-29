"""Add customer service tables.

Revision ID: add_customer_service_tables
Revises: add_tenant_end_date_and_tier
Create Date: 2024-12-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_customer_service_tables"
down_revision = "add_tenant_end_date_and_tier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tenant_customer_service_configs table
    op.create_table(
        "tenant_customer_service_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("zapier_webhook_url", sa.Text(), nullable=True),
        sa.Column("zapier_callback_secret", sa.String(255), nullable=True),
        sa.Column("customer_lookup_timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("query_timeout_seconds", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("llm_fallback_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("llm_fallback_prompt_override", sa.Text(), nullable=True),
        sa.Column("routing_rules", sa.JSON(), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tenant_customer_service_configs_id",
        "tenant_customer_service_configs",
        ["id"],
    )
    op.create_index(
        "ix_tenant_customer_service_configs_tenant_id",
        "tenant_customer_service_configs",
        ["tenant_id"],
        unique=True,
    )

    # Create zapier_requests table
    op.create_table(
        "zapier_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(100), nullable=False),
        sa.Column("request_type", sa.String(50), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("request_sent_at", sa.DateTime(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("response_received_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("phone_number", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zapier_requests_id", "zapier_requests", ["id"])
    op.create_index("ix_zapier_requests_tenant_id", "zapier_requests", ["tenant_id"])
    op.create_index(
        "ix_zapier_requests_correlation_id",
        "zapier_requests",
        ["correlation_id"],
        unique=True,
    )
    op.create_index("ix_zapier_requests_phone_number", "zapier_requests", ["phone_number"])
    op.create_index(
        "ix_zapier_requests_tenant_status",
        "zapier_requests",
        ["tenant_id", "status"],
    )

    # Create jackrabbit_customers table
    op.create_table(
        "jackrabbit_customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("jackrabbit_id", sa.String(100), nullable=False),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("customer_data", sa.JSON(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=False),
        sa.Column("cache_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jackrabbit_customers_id", "jackrabbit_customers", ["id"])
    op.create_index("ix_jackrabbit_customers_tenant_id", "jackrabbit_customers", ["tenant_id"])
    op.create_index("ix_jackrabbit_customers_jackrabbit_id", "jackrabbit_customers", ["jackrabbit_id"])
    op.create_index("ix_jackrabbit_customers_phone_number", "jackrabbit_customers", ["phone_number"])
    op.create_index("ix_jackrabbit_customers_email", "jackrabbit_customers", ["email"])
    op.create_index(
        "ix_jackrabbit_tenant_phone",
        "jackrabbit_customers",
        ["tenant_id", "phone_number"],
    )
    op.create_index(
        "ix_jackrabbit_tenant_jid",
        "jackrabbit_customers",
        ["tenant_id", "jackrabbit_id"],
    )


def downgrade() -> None:
    op.drop_table("jackrabbit_customers")
    op.drop_table("zapier_requests")
    op.drop_table("tenant_customer_service_configs")
