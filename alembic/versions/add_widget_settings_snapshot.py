"""Add settings_snapshot column to widget_events for A/B testing

Revision ID: add_widget_settings_snapshot
Revises: add_call_language
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_widget_settings_snapshot'
down_revision = 'add_call_language'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add settings_snapshot column to widget_events table
    # This stores widget appearance settings at the time of the event
    # for A/B testing analysis of which settings configurations perform best
    op.add_column(
        'widget_events',
        sa.Column('settings_snapshot', sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('widget_events', 'settings_snapshot')
