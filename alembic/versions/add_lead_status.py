"""Add status column to leads table

Revision ID: add_lead_status
Revises: 3757de506b23
Create Date: 2025-12-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_lead_status'
down_revision = '3757de506b23'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add status column to leads table
    op.add_column('leads', sa.Column('status', sa.String(length=50), nullable=True, server_default='new'))
    op.create_index(op.f('ix_leads_status'), 'leads', ['status'], unique=False)
    
    # Update existing leads to have 'new' status
    op.execute("UPDATE leads SET status = 'new' WHERE status IS NULL")


def downgrade() -> None:
    op.drop_index(op.f('ix_leads_status'), table_name='leads')
    op.drop_column('leads', 'status')
