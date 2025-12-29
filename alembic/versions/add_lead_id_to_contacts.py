"""Add lead_id to contacts table

Revision ID: add_lead_id_to_contacts
Revises: add_contacts_table
Create Date: 2025-12-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_lead_id_to_contacts'
down_revision = 'add_contacts_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('lead_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_contacts_lead_id'), 'contacts', ['lead_id'], unique=False)
    op.create_foreign_key('fk_contacts_lead_id', 'contacts', 'leads', ['lead_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_contacts_lead_id', 'contacts', type_='foreignkey')
    op.drop_index(op.f('ix_contacts_lead_id'), table_name='contacts')
    op.drop_column('contacts', 'lead_id')
