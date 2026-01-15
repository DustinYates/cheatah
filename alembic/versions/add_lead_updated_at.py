"""Add updated_at column to leads table.

Revision ID: add_lead_updated_at
Revises: auto_convert_existing_leads
Create Date: 2026-01-15
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_lead_updated_at"
down_revision = "auto_convert_existing_leads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add updated_at column, defaulting to created_at for existing rows
    op.add_column(
        "leads",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    # Set updated_at to created_at for existing leads
    op.execute("UPDATE leads SET updated_at = created_at WHERE updated_at IS NULL")

    # Make column non-nullable
    op.alter_column("leads", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("leads", "updated_at")
