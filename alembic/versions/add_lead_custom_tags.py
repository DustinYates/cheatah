"""Add custom_tags column to leads

Revision ID: add_lead_custom_tags
Revises: a1fea067b2e2
Create Date: 2026-04-19 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "add_lead_custom_tags"
down_revision = "a1fea067b2e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("custom_tags", sa.JSON(), nullable=True),
    )
    op.execute("UPDATE leads SET custom_tags = '[]'::json WHERE custom_tags IS NULL")


def downgrade() -> None:
    op.drop_column("leads", "custom_tags")
