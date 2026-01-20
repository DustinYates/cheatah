"""Add language field to calls table for tracking Spanish vs English calls

Revision ID: add_call_language
Revises: add_widget_events
Create Date: 2026-01-20

"""
from alembic import op
import sqlalchemy as sa


revision = 'add_call_language'
down_revision = 'add_multitenancy_enhancements'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add language column to calls table
    op.add_column('calls', sa.Column('language', sa.String(20), nullable=True))
    # Add index for efficient language-based queries
    op.create_index('ix_calls_language', 'calls', ['language'], unique=False)
    # Composite index for analytics queries by tenant and language
    op.create_index(
        'ix_calls_tenant_language',
        'calls',
        ['tenant_id', 'language'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_calls_tenant_language', table_name='calls')
    op.drop_index('ix_calls_language', table_name='calls')
    op.drop_column('calls', 'language')
