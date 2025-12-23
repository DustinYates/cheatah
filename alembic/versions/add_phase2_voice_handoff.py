"""Add Phase 2 voice handoff tables and columns

Revision ID: add_phase2_voice_handoff
Revises: add_call_summaries_table
Create Date: 2024-12-22 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_phase2_voice_handoff'
down_revision = 'add_call_summaries'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create tenant_voice_configs table
    op.create_table(
        'tenant_voice_configs',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, unique=True, index=True),
        sa.Column('is_enabled', sa.Boolean(), default=False, nullable=False),
        sa.Column('handoff_mode', sa.String(length=50), default='take_message', nullable=False),
        sa.Column('live_transfer_number', sa.String(length=50), nullable=True),
        sa.Column('escalation_rules', sa.JSON(), nullable=True),
        sa.Column('default_greeting', sa.Text(), nullable=True),
        sa.Column('disclosure_line', sa.Text(), nullable=True),
        sa.Column('notification_methods', sa.JSON(), nullable=True),
        sa.Column('notification_recipients', sa.JSON(), nullable=True),
        sa.Column('after_hours_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=True, index=True),
        sa.Column('notification_type', sa.String(length=50), nullable=False, index=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('is_read', sa.Boolean(), default=False, nullable=False, index=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('priority', sa.String(length=20), default='normal', nullable=False),
        sa.Column('action_url', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, index=True, server_default=sa.func.now()),
    )
    
    # Add handoff columns to calls table
    op.add_column('calls', sa.Column('handoff_attempted', sa.Boolean(), default=False, nullable=True))
    op.add_column('calls', sa.Column('handoff_number', sa.String(length=50), nullable=True))
    op.add_column('calls', sa.Column('handoff_reason', sa.String(length=100), nullable=True))
    
    # Set default value for existing rows and make not nullable
    op.execute("UPDATE calls SET handoff_attempted = FALSE WHERE handoff_attempted IS NULL")
    op.alter_column('calls', 'handoff_attempted', nullable=False)


def downgrade() -> None:
    # Remove handoff columns from calls table
    op.drop_column('calls', 'handoff_reason')
    op.drop_column('calls', 'handoff_number')
    op.drop_column('calls', 'handoff_attempted')
    
    # Drop notifications table
    op.drop_table('notifications')
    
    # Drop tenant_voice_configs table
    op.drop_table('tenant_voice_configs')

