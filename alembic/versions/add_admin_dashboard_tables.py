"""Add admin dashboard tables: health snapshots, anomaly alerts, SMS burst detection, CHI fields

Revision ID: add_admin_dashboard_tables
Revises: add_tenant_calendar_configs
Create Date: 2026-01-31

Adds:
- communications_health_snapshots: pre-aggregated hourly metrics
- anomaly_alerts: detected anomalies in metrics
- sms_burst_incidents: SMS burst/spam incident tracking
- sms_burst_configs: per-tenant burst detection thresholds
- conversations: chi_score, chi_computed_at, chi_signals columns
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_admin_dashboard_tables'
down_revision = 'add_tenant_calendar_configs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- communications_health_snapshots ---
    op.create_table(
        'communications_health_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_date', sa.DateTime(), nullable=False),
        sa.Column('snapshot_hour', sa.Integer(), nullable=True),
        # Channel volume
        sa.Column('total_calls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('inbound_calls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('outbound_calls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_sms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('inbound_sms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('outbound_sms', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_emails', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('inbound_emails', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('outbound_emails', sa.Integer(), nullable=False, server_default='0'),
        # Call duration
        sa.Column('total_call_minutes', sa.Float(), nullable=False, server_default='0'),
        sa.Column('avg_call_duration_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('median_call_duration_seconds', sa.Float(), nullable=False, server_default='0'),
        sa.Column('short_calls_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('long_calls_count', sa.Integer(), nullable=False, server_default='0'),
        # Bot vs human
        sa.Column('bot_handled_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('human_handled_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('escalated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bot_resolution_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_time_to_escalation_seconds', sa.Float(), nullable=False, server_default='0'),
        # Reliability
        sa.Column('dropped_calls_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_calls_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_sms_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bounced_emails_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('api_errors_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'snapshot_date', 'snapshot_hour', name='uix_tenant_snapshot_date_hour'),
    )
    op.create_index('ix_snapshot_tenant_date', 'communications_health_snapshots', ['tenant_id', 'snapshot_date'])

    # --- anomaly_alerts ---
    op.create_table(
        'anomaly_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('alert_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='warning'),
        sa.Column('metric_name', sa.String(length=100), nullable=False),
        sa.Column('current_value', sa.Float(), nullable=False),
        sa.Column('baseline_value', sa.Float(), nullable=False),
        sa.Column('threshold_percent', sa.Float(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('detected_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_anomaly_tenant_detected', 'anomaly_alerts', ['tenant_id', 'detected_at'])
    op.create_index('ix_anomaly_status', 'anomaly_alerts', ['status'])

    # --- sms_burst_incidents ---
    op.create_table(
        'sms_burst_incidents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('to_number', sa.String(length=50), nullable=False),
        sa.Column('message_count', sa.Integer(), nullable=False),
        sa.Column('first_message_at', sa.DateTime(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(), nullable=False),
        sa.Column('time_window_seconds', sa.Integer(), nullable=False),
        sa.Column('avg_gap_seconds', sa.Float(), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='warning'),
        sa.Column('has_identical_content', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('content_similarity_score', sa.Float(), nullable=True),
        sa.Column('likely_cause', sa.String(length=100), nullable=True),
        sa.Column('handler', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('auto_blocked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_burst_tenant_detected', 'sms_burst_incidents', ['tenant_id', 'detected_at'])
    op.create_index('ix_burst_status_severity', 'sms_burst_incidents', ['status', 'severity'])
    op.create_index('ix_burst_tenant_number', 'sms_burst_incidents', ['tenant_id', 'to_number'])

    # --- sms_burst_configs ---
    op.create_table(
        'sms_burst_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('time_window_seconds', sa.Integer(), nullable=False, server_default='180'),
        sa.Column('message_threshold', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('high_severity_threshold', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('rapid_gap_min_seconds', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('rapid_gap_max_seconds', sa.Integer(), nullable=False, server_default='29'),
        sa.Column('identical_content_threshold', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('similarity_threshold', sa.Float(), nullable=False, server_default='0.9'),
        sa.Column('auto_block_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('auto_block_threshold', sa.Integer(), nullable=False, server_default='10'),
        sa.Column('excluded_flows', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', name='uix_burst_config_tenant'),
    )

    # --- Add CHI columns to conversations ---
    op.add_column('conversations', sa.Column('chi_score', sa.Float(), nullable=True))
    op.add_column('conversations', sa.Column('chi_computed_at', sa.DateTime(), nullable=True))
    op.add_column('conversations', sa.Column('chi_signals', sa.JSON(), nullable=True))
    op.create_index('ix_conversations_chi_score', 'conversations', ['chi_score'])


def downgrade() -> None:
    op.drop_index('ix_conversations_chi_score', table_name='conversations')
    op.drop_column('conversations', 'chi_signals')
    op.drop_column('conversations', 'chi_computed_at')
    op.drop_column('conversations', 'chi_score')
    op.drop_table('sms_burst_configs')
    op.drop_table('sms_burst_incidents')
    op.drop_table('anomaly_alerts')
    op.drop_table('communications_health_snapshots')
