"""Add widget_events table for tracking widget engagement analytics

Revision ID: add_widget_events
Revises: add_prompt_channel
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_widget_events'
down_revision = 'add_prompt_channel'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create widget_events table
    op.create_table(
        'widget_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('visitor_id', sa.String(100), nullable=False),
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('event_data', sa.JSON(), nullable=True),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('device_type', sa.String(20), nullable=True),
        sa.Column('client_timestamp', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # Primary key index
    op.create_index('ix_widget_events_id', 'widget_events', ['id'], unique=False)
    # Foreign key index
    op.create_index('ix_widget_events_tenant_id', 'widget_events', ['tenant_id'], unique=False)
    # Event type index for filtering
    op.create_index('ix_widget_events_event_type', 'widget_events', ['event_type'], unique=False)
    # Visitor ID index for session tracking
    op.create_index('ix_widget_events_visitor_id', 'widget_events', ['visitor_id'], unique=False)
    # Session ID index for linking to chat sessions
    op.create_index('ix_widget_events_session_id', 'widget_events', ['session_id'], unique=False)
    # Created at index for date range queries
    op.create_index('ix_widget_events_created_at', 'widget_events', ['created_at'], unique=False)
    # Composite index for efficient analytics queries
    op.create_index(
        'ix_widget_events_tenant_type_date',
        'widget_events',
        ['tenant_id', 'event_type', 'created_at'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_widget_events_tenant_type_date', table_name='widget_events')
    op.drop_index('ix_widget_events_created_at', table_name='widget_events')
    op.drop_index('ix_widget_events_session_id', table_name='widget_events')
    op.drop_index('ix_widget_events_visitor_id', table_name='widget_events')
    op.drop_index('ix_widget_events_event_type', table_name='widget_events')
    op.drop_index('ix_widget_events_tenant_id', table_name='widget_events')
    op.drop_index('ix_widget_events_id', table_name='widget_events')
    op.drop_table('widget_events')
