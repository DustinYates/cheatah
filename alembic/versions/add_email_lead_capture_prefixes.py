"""Add lead_capture_subject_prefixes to tenant_email_configs

Revision ID: add_email_lead_prefixes
Revises: add_email_responder
Create Date: 2024-12-24 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_email_lead_prefixes'
down_revision = 'add_email_responder'
branch_labels = None
depends_on = None

# Default prefixes for lead capture
DEFAULT_PREFIXES = ["Email Capture from Booking Page", "Get In Touch Form Submission"]


def upgrade() -> None:
    # Add lead_capture_subject_prefixes column to tenant_email_configs
    op.add_column(
        'tenant_email_configs',
        sa.Column('lead_capture_subject_prefixes', sa.JSON(), nullable=True)
    )
    
    # Set default value for existing rows
    op.execute(
        f"UPDATE tenant_email_configs SET lead_capture_subject_prefixes = '{str(DEFAULT_PREFIXES).replace(chr(39), chr(34))}' WHERE lead_capture_subject_prefixes IS NULL"
    )


def downgrade() -> None:
    op.drop_column('tenant_email_configs', 'lead_capture_subject_prefixes')

