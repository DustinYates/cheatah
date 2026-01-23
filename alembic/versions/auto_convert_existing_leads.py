"""Auto-convert existing qualifying leads to contacts

Revision ID: auto_convert_existing_leads
Revises: add_tenant_prompt_config
Create Date: 2026-01-12

This migration finds all leads that:
1. Have a name (not NULL/empty)
2. Have either email OR phone (at least one)
3. Don't already have a linked contact (via lead_id FK)

For each qualifying lead, it creates a contact record or links to existing contact.
"""
from alembic import op
from sqlalchemy import text
from datetime import datetime


revision = 'auto_convert_existing_leads'
down_revision = 'add_tenant_prompt_config'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Convert qualifying leads to contacts."""
    connection = op.get_bind()

    # Find all qualifying leads that don't already have contacts
    # A lead qualifies if it has name AND (email OR phone)
    # Exclude leads that already have a contact pointing to them
    qualifying_leads_query = text("""
        SELECT l.id, l.tenant_id, l.email, l.phone, l.name, l.extra_data
        FROM leads l
        LEFT JOIN contacts c ON c.lead_id = l.id
        WHERE c.id IS NULL
          AND l.name IS NOT NULL
          AND l.name != ''
          AND (
              (l.email IS NOT NULL AND l.email != '')
              OR (l.phone IS NOT NULL AND l.phone != '')
          )
        ORDER BY l.id
    """)

    result = connection.execute(qualifying_leads_query)
    leads_to_convert = result.fetchall()

    print(f"Found {len(leads_to_convert)} qualifying leads to convert")

    converted_count = 0
    linked_count = 0

    for lead in leads_to_convert:
        lead_id = lead[0]
        tenant_id = lead[1]
        email = lead[2]
        phone = lead[3]
        name = lead[4]
        extra_data = lead[5]

        # Check if a contact already exists with this email or phone
        # (to avoid duplicates - matches existing logic in _create_contact_from_lead)
        existing_contact_query = text("""
            SELECT id FROM contacts
            WHERE tenant_id = :tenant_id
              AND deleted_at IS NULL
              AND merged_into_contact_id IS NULL
              AND (
                  (:email IS NOT NULL AND email = :email)
                  OR (:phone IS NOT NULL AND phone = :phone)
              )
            LIMIT 1
        """)

        existing = connection.execute(
            existing_contact_query,
            {"tenant_id": tenant_id, "email": email, "phone": phone}
        ).fetchone()

        if existing:
            # Link existing contact to this lead
            existing_contact_id = existing[0]
            connection.execute(
                text("UPDATE contacts SET lead_id = :lead_id WHERE id = :contact_id AND lead_id IS NULL"),
                {"lead_id": lead_id, "contact_id": existing_contact_id}
            )
            print(f"Linked lead {lead_id} to existing contact {existing_contact_id}")
            linked_count += 1
        else:
            # Create new contact
            # Determine source based on extra_data
            source = 'auto_convert_migration'
            if extra_data and isinstance(extra_data, dict):
                if extra_data.get('source') == 'voice_call':
                    source = 'voice_call'

            connection.execute(
                text("""
                    INSERT INTO contacts (tenant_id, lead_id, email, phone, name, source, created_at)
                    VALUES (:tenant_id, :lead_id, :email, :phone, :name, :source, :created_at)
                """),
                {
                    "tenant_id": tenant_id,
                    "lead_id": lead_id,
                    "email": email,
                    "phone": phone,
                    "name": name,
                    "source": source,
                    "created_at": datetime.utcnow()
                }
            )
            print(f"Created contact for lead {lead_id}: {name}, {email or phone}")
            converted_count += 1

    print(f"Migration complete: {converted_count} contacts created, {linked_count} leads linked to existing contacts")


def downgrade() -> None:
    """Remove auto-converted contacts.

    Note: This only removes contacts created by this migration (source='auto_convert_migration').
    Contacts that were linked to existing records are NOT unlinked.
    """
    connection = op.get_bind()

    # Delete contacts created by this migration
    result = connection.execute(
        text("DELETE FROM contacts WHERE source = 'auto_convert_migration'")
    )

    print(f"Downgrade: Removed {result.rowcount} auto-converted contacts")
