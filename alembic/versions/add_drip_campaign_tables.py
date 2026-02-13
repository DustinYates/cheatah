"""add_drip_campaign_tables

Revision ID: a1b2c3d4e5f6
Revises: 27e99ad1ae35
Create Date: 2026-02-13 16:00:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '27e99ad1ae35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default response templates for BSS tenants
BSS_RESPONSE_TEMPLATES = {
    "price": {
        "keywords": ["price", "cost", "how much", "fee", "expensive", "afford", "pricing", "rates"],
        "reply": (
            "Lessons are $35 per lesson and billed monthly. "
            "Most start once weekly, and some choose twice weekly for faster progress with a 10% discount. "
            "Which option were you considering?\n\n"
            "I can send you right back to the final step to secure your spot if you're ready!"
        ),
    },
    "spouse": {
        "keywords": ["husband", "wife", "spouse", "partner", "check with", "talk to", "ask my"],
        "reply": (
            "Totally understand! Classes do fill as families complete registration, "
            "so once you're ready I can send the final link to lock it in. "
            "Want me to resend the final step now so you have it handy?"
        ),
    },
    "schedule": {
        "keywords": ["twice", "two times", "2x", "second day", "another day", "different day", "back to back", "twice a week"],
        "reply": (
            "We can absolutely look at adding a second day! "
            "Would you prefer back-to-back or different days? "
            "Once we confirm, I'll send the updated final registration link."
        ),
    },
    "sibling": {
        "keywords": ["sibling", "brother", "sister", "both kids", "another child", "other kid", "two kids", "both children"],
        "reply": (
            "I can enroll both together! "
            "Would you prefer same-time classes or back-to-back? "
            "I'll send one final link once we finalize both placements."
        ),
    },
    "yes_link": {
        "keywords": ["yes", "ready", "send it", "send link", "sign up", "register", "let's do it", "go ahead", "sure", "please"],
        "action": "send_registration_link",
    },
    "not_interested": {
        "keywords": ["no", "not interested", "stop", "cancel", "unsubscribe", "remove", "not right now"],
        "action": "cancel_drip",
    },
}


def upgrade() -> None:
    # 1. Create drip_campaigns table
    op.create_table(
        'drip_campaigns',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('campaign_type', sa.String(length=50), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('trigger_delay_minutes', sa.Integer(), nullable=False, server_default=sa.text('10')),
        sa.Column('response_templates', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'campaign_type', name='uq_drip_campaign_tenant_type'),
    )

    # 2. Create drip_campaign_steps table
    op.create_table(
        'drip_campaign_steps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('drip_campaigns.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('step_number', sa.Integer(), nullable=False),
        sa.Column('delay_minutes', sa.Integer(), nullable=False),
        sa.Column('message_template', sa.Text(), nullable=False),
        sa.Column('check_availability', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('fallback_template', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('campaign_id', 'step_number', name='uq_drip_step_campaign_number'),
    )

    # 3. Create drip_enrollments table
    op.create_table(
        'drip_enrollments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('campaign_id', sa.Integer(), sa.ForeignKey('drip_campaigns.id'), nullable=False, index=True),
        sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=False, index=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='active', index=True),
        sa.Column('current_step', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('next_task_id', sa.String(length=500), nullable=True),
        sa.Column('next_step_at', sa.DateTime(), nullable=True),
        sa.Column('context_data', sa.JSON(), nullable=True),
        sa.Column('response_category', sa.String(length=50), nullable=True),
        sa.Column('cancelled_reason', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id', 'campaign_id', 'lead_id', name='uq_drip_enrollment_tenant_campaign_lead'),
    )

    # 4. Add drip_campaign_enabled to tenant_email_configs
    op.add_column(
        'tenant_email_configs',
        sa.Column('drip_campaign_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )

    # 5. Enable RLS on all three tables
    op.execute("ALTER TABLE drip_campaigns ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE drip_campaign_steps ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE drip_enrollments ENABLE ROW LEVEL SECURITY")

    # 6. Create RLS policies
    op.execute("""
        CREATE POLICY drip_campaigns_tenant_isolation ON drip_campaigns
        USING (tenant_id = current_setting('app.current_tenant_id', true)::int)
    """)
    op.execute("""
        CREATE POLICY drip_campaign_steps_tenant_isolation ON drip_campaign_steps
        USING (campaign_id IN (
            SELECT id FROM drip_campaigns
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::int
        ))
    """)
    op.execute("""
        CREATE POLICY drip_enrollments_tenant_isolation ON drip_enrollments
        USING (tenant_id = current_setting('app.current_tenant_id', true)::int)
    """)

    # 7. Seed default campaigns for tenant 3 (BSS Cypress-Spring)
    templates_json = json.dumps(BSS_RESPONSE_TEMPLATES).replace("'", "''")

    # Kids campaign
    op.execute(f"""
        INSERT INTO drip_campaigns (tenant_id, name, campaign_type, is_enabled, trigger_delay_minutes, response_templates)
        VALUES (3, 'Kids Registration Drip', 'kids', false, 10, '{templates_json}'::jsonb)
        ON CONFLICT (tenant_id, campaign_type) DO NOTHING
    """)

    # Adults campaign
    op.execute(f"""
        INSERT INTO drip_campaigns (tenant_id, name, campaign_type, is_enabled, trigger_delay_minutes, response_templates)
        VALUES (3, 'Adults Registration Drip', 'adults', false, 10, '{templates_json}'::jsonb)
        ON CONFLICT (tenant_id, campaign_type) DO NOTHING
    """)

    # Kids steps
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 1, 10,
            'Hi {{First Name}}! This is British Swim School. We noticed you started enrolling for swim lessons but didn''t finish. Do you have any questions I can help with?',
            false, NULL
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'kids'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 2, 1440,
            'Hi {{First Name}}! Before that class fills, did you want clarification on pricing, sibling discounts, or adding a second day?',
            false, NULL
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'kids'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 3, 2880,
            'Hi {{First Name}}! We''d love to help build water safety skills. Let me know if anything is preventing you from finishing enrollment.',
            false, NULL
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'kids'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 4, 7200,
            'Hi {{First Name}}! That class is still showing availability right now! Want the final link to secure it?',
            true,
            'Hi {{First Name}}! When you''re ready to move forward, I can send the final step to complete enrollment.'
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'kids'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)

    # Adults steps
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 1, 10,
            'Hi {{First Name}}! This is British Swim School. We noticed you were almost finished enrolling for swim lessons. What questions can I answer?',
            false, NULL
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'adults'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 2, 1440,
            'Hi {{First Name}}! Most adults ask about pricing or scheduling before finishing. Happy to clarify anything. What would help you decide?',
            false, NULL
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'adults'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 3, 2880,
            'Hi {{First Name}}! We''re still showing availability for evening classes. Want me to send the final registration link?',
            true,
            'Hi {{First Name}}! When you''re ready to move forward, I can send the final step to secure your class.'
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'adults'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)
    op.execute("""
        INSERT INTO drip_campaign_steps (campaign_id, step_number, delay_minutes, message_template, check_availability, fallback_template)
        SELECT id, 4, 7200,
            'Hi {{First Name}}! When you''re ready to move forward, I can send the final step to secure your class.',
            false, NULL
        FROM drip_campaigns WHERE tenant_id = 3 AND campaign_type = 'adults'
        ON CONFLICT (campaign_id, step_number) DO NOTHING
    """)


def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS drip_enrollments_tenant_isolation ON drip_enrollments")
    op.execute("DROP POLICY IF EXISTS drip_campaign_steps_tenant_isolation ON drip_campaign_steps")
    op.execute("DROP POLICY IF EXISTS drip_campaigns_tenant_isolation ON drip_campaigns")

    # Drop tables (reverse order due to FKs)
    op.drop_table('drip_enrollments')
    op.drop_table('drip_campaign_steps')
    op.drop_table('drip_campaigns')

    # Remove column from tenant_email_configs
    op.drop_column('tenant_email_configs', 'drip_campaign_enabled')
