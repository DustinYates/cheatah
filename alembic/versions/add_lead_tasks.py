"""Add lead_tasks table

Revision ID: add_lead_tasks
Revises: add_outlook_email_columns
Create Date: 2026-03-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_lead_tasks'
down_revision = 'add_outlook_email_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'lead_tasks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('is_completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_lead_tasks_tenant_id', 'lead_tasks', ['tenant_id'])
    op.create_index('ix_lead_tasks_lead_id', 'lead_tasks', ['lead_id'])
    op.create_index('ix_lead_tasks_due_date', 'lead_tasks', ['due_date'])

    # RLS policy
    op.execute("ALTER TABLE lead_tasks ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY lead_tasks_tenant_isolation ON lead_tasks
        USING (tenant_id = current_setting('app.current_tenant_id')::int)
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS lead_tasks_tenant_isolation ON lead_tasks")
    op.drop_index('ix_lead_tasks_due_date', table_name='lead_tasks')
    op.drop_index('ix_lead_tasks_lead_id', table_name='lead_tasks')
    op.drop_index('ix_lead_tasks_tenant_id', table_name='lead_tasks')
    op.drop_table('lead_tasks')
