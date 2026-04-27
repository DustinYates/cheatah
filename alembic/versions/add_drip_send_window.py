"""Add send_window_start/end to drip_campaigns

Revision ID: add_drip_send_window
Revises: add_drip_affects_pipeline
Create Date: 2026-04-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_drip_send_window'
down_revision = 'add_drip_affects_pipeline'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'drip_campaigns',
        sa.Column(
            'send_window_start',
            sa.String(length=5),
            nullable=False,
            server_default='08:00',
        ),
    )
    op.add_column(
        'drip_campaigns',
        sa.Column(
            'send_window_end',
            sa.String(length=5),
            nullable=False,
            server_default='21:00',
        ),
    )


def downgrade() -> None:
    op.drop_column('drip_campaigns', 'send_window_end')
    op.drop_column('drip_campaigns', 'send_window_start')
