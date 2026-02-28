"""add_tenant_pipeline_stages

Revision ID: c2560f828035
Revises: 790dc75e8559
Create Date: 2026-02-28 10:52:11.302527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2560f828035'
down_revision: Union[str, None] = '790dc75e8559'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tenant_pipeline_stages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=False, server_default='#6b7280'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'key', name='uq_tenant_pipeline_stage_key'),
    )
    op.create_index('ix_tenant_pipeline_stages_tenant_id', 'tenant_pipeline_stages', ['tenant_id'])

    # Seed default stages for all existing tenants
    conn = op.get_bind()
    tenant_ids = conn.execute(sa.text("SELECT id FROM tenants")).fetchall()

    defaults = [
        ('new_lead', 'New Lead', '#1d4ed8', 0),
        ('contacted', 'Contacted', '#b45309', 1),
        ('interested', 'Interested', '#be185d', 2),
        ('registered', 'Registered', '#047857', 3),
        ('enrolled', 'Enrolled', '#4338ca', 4),
    ]

    for (tid,) in tenant_ids:
        for key, label, color, position in defaults:
            conn.execute(sa.text(
                "INSERT INTO tenant_pipeline_stages (tenant_id, key, label, color, position) "
                "VALUES (:tid, :key, :label, :color, :pos)"
            ), {"tid": tid, "key": key, "label": label, "color": color, "pos": position})


def downgrade() -> None:
    op.drop_index('ix_tenant_pipeline_stages_tenant_id', table_name='tenant_pipeline_stages')
    op.drop_table('tenant_pipeline_stages')
