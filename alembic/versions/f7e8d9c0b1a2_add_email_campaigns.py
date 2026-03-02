"""add_email_campaigns

Revision ID: f7e8d9c0b1a2
Revises: c2560f828035
Create Date: 2026-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f7e8d9c0b1a2'
down_revision: Union[str, None] = 'c2560f828035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Email campaigns table
    op.create_table(
        'email_campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='draft'),
        sa.Column('subject_template', sa.String(length=500), nullable=False),
        sa.Column('email_prompt_instructions', sa.Text(), nullable=True),
        sa.Column('from_email', sa.String(length=255), nullable=True),
        sa.Column('reply_to', sa.String(length=255), nullable=True),
        sa.Column('unsubscribe_url', sa.String(length=500), nullable=False),
        sa.Column('physical_address', sa.String(length=500), nullable=False),
        sa.Column('send_at', sa.DateTime(), nullable=True),
        sa.Column('batch_size', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('batch_delay_seconds', sa.Integer(), nullable=False, server_default='300'),
        sa.Column('total_recipients', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'name', name='uq_email_campaign_tenant_name'),
    )
    op.create_index('ix_email_campaigns_id', 'email_campaigns', ['id'])
    op.create_index('ix_email_campaigns_tenant_id', 'email_campaigns', ['tenant_id'])
    op.create_index('ix_email_campaigns_status', 'email_campaigns', ['status'])

    # Email campaign recipients table
    op.create_table(
        'email_campaign_recipients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('contact_id', sa.Integer(), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('company', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=255), nullable=True),
        sa.Column('personalization_data', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('generated_subject', sa.String(length=500), nullable=True),
        sa.Column('generated_body', sa.Text(), nullable=True),
        sa.Column('sendgrid_message_id', sa.String(length=255), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['campaign_id'], ['email_campaigns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campaign_id', 'email', name='uq_email_recipient_campaign_email'),
    )
    op.create_index('ix_email_campaign_recipients_id', 'email_campaign_recipients', ['id'])
    op.create_index('ix_email_campaign_recipients_campaign_id', 'email_campaign_recipients', ['campaign_id'])
    op.create_index('ix_email_campaign_recipients_tenant_id', 'email_campaign_recipients', ['tenant_id'])
    op.create_index('ix_email_campaign_recipients_status', 'email_campaign_recipients', ['status'])

    # Enable RLS
    op.execute("ALTER TABLE email_campaigns ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY email_campaigns_tenant_isolation ON email_campaigns "
        "USING (tenant_id::text = current_setting('app.current_tenant_id', true))"
    )
    op.execute("ALTER TABLE email_campaign_recipients ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY email_campaign_recipients_tenant_isolation ON email_campaign_recipients "
        "USING (tenant_id::text = current_setting('app.current_tenant_id', true))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS email_campaign_recipients_tenant_isolation ON email_campaign_recipients")
    op.execute("DROP POLICY IF EXISTS email_campaigns_tenant_isolation ON email_campaigns")
    op.drop_index('ix_email_campaign_recipients_status', table_name='email_campaign_recipients')
    op.drop_index('ix_email_campaign_recipients_tenant_id', table_name='email_campaign_recipients')
    op.drop_index('ix_email_campaign_recipients_campaign_id', table_name='email_campaign_recipients')
    op.drop_index('ix_email_campaign_recipients_id', table_name='email_campaign_recipients')
    op.drop_table('email_campaign_recipients')
    op.drop_index('ix_email_campaigns_status', table_name='email_campaigns')
    op.drop_index('ix_email_campaigns_tenant_id', table_name='email_campaigns')
    op.drop_index('ix_email_campaigns_id', table_name='email_campaigns')
    op.drop_table('email_campaigns')
