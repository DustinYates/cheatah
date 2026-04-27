"""add sms_templates

Revision ID: add_sms_templates
Revises: add_drip_send_window
Create Date: 2026-04-27 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_sms_templates'
down_revision: Union[str, None] = 'add_drip_send_window'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sms_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_sms_template_tenant_name'),
    )
    op.create_index('ix_sms_templates_id', 'sms_templates', ['id'])
    op.create_index('ix_sms_templates_tenant_id', 'sms_templates', ['tenant_id'])

    op.execute("ALTER TABLE sms_templates ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY sms_templates_tenant_isolation ON sms_templates "
        "USING (tenant_id::text = current_setting('app.current_tenant_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS sms_templates_tenant_isolation ON sms_templates")
    op.drop_index('ix_sms_templates_tenant_id', table_name='sms_templates')
    op.drop_index('ix_sms_templates_id', table_name='sms_templates')
    op.drop_table('sms_templates')
