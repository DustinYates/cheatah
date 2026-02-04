"""Add admin notification tracking columns and service_health_incidents table

Adds admin_notified_at to anomaly_alerts and sms_burst_incidents for deduplication.
Creates service_health_incidents table for tracking external service failures.

Revision ID: add_admin_notification_tracking
Revises: add_contact_profile_fields
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'add_admin_notification_tracking'
down_revision: Union[str, None] = 'add_contact_profile_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add admin_notified_at to anomaly_alerts
    op.add_column(
        'anomaly_alerts',
        sa.Column('admin_notified_at', sa.DateTime(), nullable=True)
    )

    # Add admin_notified_at to sms_burst_incidents
    op.add_column(
        'sms_burst_incidents',
        sa.Column('admin_notified_at', sa.DateTime(), nullable=True)
    )

    # Create service_health_incidents table
    op.create_table(
        'service_health_incidents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=True),  # NULL for global incidents
        sa.Column('service_name', sa.String(50), nullable=False),  # telnyx, gmail, gemini, etc.
        sa.Column('error_type', sa.String(100), nullable=False),  # timeout, auth_failed, rate_limited
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('first_error_at', sa.DateTime(), nullable=False),
        sa.Column('last_error_at', sa.DateTime(), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='warning'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('admin_notified_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        'ix_service_health_service_status',
        'service_health_incidents',
        ['service_name', 'status']
    )
    op.create_index(
        'ix_service_health_tenant_status',
        'service_health_incidents',
        ['tenant_id', 'status']
    )


def downgrade() -> None:
    op.drop_index('ix_service_health_tenant_status', table_name='service_health_incidents')
    op.drop_index('ix_service_health_service_status', table_name='service_health_incidents')
    op.drop_table('service_health_incidents')
    op.drop_column('sms_burst_incidents', 'admin_notified_at')
    op.drop_column('anomaly_alerts', 'admin_notified_at')
