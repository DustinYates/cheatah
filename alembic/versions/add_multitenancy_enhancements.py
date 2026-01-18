"""Add multi-tenancy enhancements: soft delete, audit logs, RLS

Revision ID: add_multitenancy_enhancements
Revises: 0e0a47c4ec9a_add_prompt_status_and_scope
Create Date: 2026-01-18

This migration adds:
1. Soft delete columns to tenants table (deleted_at, deleted_by, updated_at)
2. Audit logs table for tracking sensitive operations
3. Row-Level Security (RLS) policies for defense-in-depth tenant isolation
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_multitenancy_enhancements'
down_revision = 'add_widget_events'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add soft delete and updated_at columns to tenants table
    op.add_column('tenants', sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now()))
    op.add_column('tenants', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column('tenants', sa.Column('deleted_by', sa.Integer(), nullable=True))

    # Add foreign key for deleted_by
    op.create_foreign_key(
        'fk_tenants_deleted_by_users',
        'tenants', 'users',
        ['deleted_by'], ['id']
    )

    # Create index on deleted_at for efficient filtering
    op.create_index('ix_tenants_deleted_at', 'tenants', ['deleted_at'])

    # 2. Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('user_email', sa.String(length=255), nullable=True),
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('tenant_name', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=True),
        sa.Column('resource_id', sa.Integer(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for audit_logs
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'])

    # 3. Add Row-Level Security (RLS) policies
    # Note: RLS requires PostgreSQL and the application must set the tenant context
    # via SET app.current_tenant_id before queries

    # Create the function to get current tenant ID from session variable
    op.execute("""
        CREATE OR REPLACE FUNCTION get_current_tenant_id()
        RETURNS INTEGER AS $$
        BEGIN
            RETURN NULLIF(current_setting('app.current_tenant_id', true), '')::INTEGER;
        EXCEPTION
            WHEN OTHERS THEN
                RETURN NULL;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # List of tables that should have RLS enabled
    # Only tables with direct tenant_id column (not inherited via FK)
    tenant_scoped_tables = [
        'contacts',
        'leads',
        'conversations',
        'calls',
        'escalations',
        'sms_opt_ins',
        'notifications',
        'widget_events',
        'email_conversations',
        'contact_merge_logs',
        'zapier_requests',
        'jackrabbit_customers',
    ]

    for table in tenant_scoped_tables:
        # Enable RLS on the table
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

        # Create policy for SELECT - users can only see their tenant's data
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation_select ON {table}
            FOR SELECT
            USING (
                tenant_id = get_current_tenant_id()
                OR get_current_tenant_id() IS NULL  -- Allow global admin access
            );
        """)

        # Create policy for INSERT - users can only insert to their tenant
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation_insert ON {table}
            FOR INSERT
            WITH CHECK (
                tenant_id = get_current_tenant_id()
                OR get_current_tenant_id() IS NULL
            );
        """)

        # Create policy for UPDATE - users can only update their tenant's data
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation_update ON {table}
            FOR UPDATE
            USING (
                tenant_id = get_current_tenant_id()
                OR get_current_tenant_id() IS NULL
            )
            WITH CHECK (
                tenant_id = get_current_tenant_id()
                OR get_current_tenant_id() IS NULL
            );
        """)

        # Create policy for DELETE - users can only delete their tenant's data
        op.execute(f"""
            CREATE POLICY {table}_tenant_isolation_delete ON {table}
            FOR DELETE
            USING (
                tenant_id = get_current_tenant_id()
                OR get_current_tenant_id() IS NULL
            );
        """)

    # Note: The application must execute:
    # SET app.current_tenant_id = '<tenant_id>';
    # before running queries for RLS to take effect.
    # This is handled by the SQLAlchemy event listeners.


def downgrade() -> None:
    # List of tables with RLS enabled
    tenant_scoped_tables = [
        'contacts',
        'leads',
        'conversations',
        'calls',
        'escalations',
        'sms_opt_ins',
        'notifications',
        'widget_events',
        'email_conversations',
        'contact_merge_logs',
        'zapier_requests',
        'jackrabbit_customers',
    ]

    # Drop RLS policies
    for table in tenant_scoped_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation_select ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation_insert ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation_update ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation_delete ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Drop the helper function
    op.execute("DROP FUNCTION IF EXISTS get_current_tenant_id();")

    # Drop audit_logs table
    op.drop_index('ix_audit_logs_created_at', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action', table_name='audit_logs')
    op.drop_index('ix_audit_logs_tenant_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_user_id', table_name='audit_logs')
    op.drop_table('audit_logs')

    # Drop tenant soft delete columns
    op.drop_index('ix_tenants_deleted_at', table_name='tenants')
    op.drop_constraint('fk_tenants_deleted_by_users', 'tenants', type_='foreignkey')
    op.drop_column('tenants', 'deleted_by')
    op.drop_column('tenants', 'deleted_at')
    op.drop_column('tenants', 'updated_at')
