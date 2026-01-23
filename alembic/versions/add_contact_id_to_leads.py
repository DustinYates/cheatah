"""Add contact_id to leads table for one-to-many relationship

Revision ID: add_contact_id_to_leads
Revises: add_do_not_contact
Create Date: 2026-01-23

This migration reverses the Lead-Contact relationship direction.
Previously: Contact had lead_id (one contact -> one lead)
Now: Lead has contact_id (many leads -> one contact)

This allows multiple leads to be associated with the same contact,
enabling each phone call to create a separate lead while maintaining
contact information at the contact level.
"""
from alembic import op
import sqlalchemy as sa


revision = 'add_contact_id_to_leads'
down_revision = 'add_do_not_contact'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add contact_id column to leads table and migrate existing data."""
    # Add contact_id column to leads
    op.add_column('leads', sa.Column('contact_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_leads_contact_id'), 'leads', ['contact_id'])
    op.create_foreign_key(
        'fk_leads_contact_id_contacts',
        'leads',
        'contacts',
        ['contact_id'],
        ['id']
    )

    # Migrate existing data: Set lead.contact_id from contact.lead_id
    # This preserves existing relationships during the transition
    op.execute("""
        UPDATE leads l
        SET contact_id = c.id
        FROM contacts c
        WHERE c.lead_id = l.id
          AND c.deleted_at IS NULL
    """)


def downgrade() -> None:
    """Remove contact_id column from leads table."""
    op.drop_constraint('fk_leads_contact_id_contacts', 'leads', type_='foreignkey')
    op.drop_index(op.f('ix_leads_contact_id'), table_name='leads')
    op.drop_column('leads', 'contact_id')
