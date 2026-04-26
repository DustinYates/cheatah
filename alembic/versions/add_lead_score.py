"""Add lead scoring fields

Revision ID: add_lead_score
Revises: add_auto_enroll_new_leads
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_lead_score'
down_revision = 'add_auto_enroll_new_leads'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'leads',
        sa.Column('score', sa.Integer(), nullable=False, server_default=sa.text('0')),
    )
    op.add_column(
        'leads',
        sa.Column(
            'score_band',
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'cold'"),
        ),
    )
    op.add_column(
        'leads',
        sa.Column('score_updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_leads_tenant_score',
        'leads',
        ['tenant_id', sa.text('score DESC')],
    )


def downgrade() -> None:
    op.drop_index('ix_leads_tenant_score', table_name='leads')
    op.drop_column('leads', 'score_updated_at')
    op.drop_column('leads', 'score_band')
    op.drop_column('leads', 'score')
