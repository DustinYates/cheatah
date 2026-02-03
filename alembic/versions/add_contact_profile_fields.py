"""Add profile fields to contacts table

Adds location, company, role, tags, and notes fields to support
the GitHub-style contact profile redesign.

Revision ID: add_contact_profile_fields
Revises: 85f97ceebafb
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'add_contact_profile_fields'
down_revision: Union[str, None] = '85f97ceebafb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add profile fields to contacts table
    op.add_column('contacts', sa.Column('location', sa.String(255), nullable=True))
    op.add_column('contacts', sa.Column('company', sa.String(255), nullable=True))
    op.add_column('contacts', sa.Column('role', sa.String(255), nullable=True))
    op.add_column('contacts', sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('contacts', sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'notes')
    op.drop_column('contacts', 'tags')
    op.drop_column('contacts', 'role')
    op.drop_column('contacts', 'company')
    op.drop_column('contacts', 'location')
