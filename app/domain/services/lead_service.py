"""Lead service for managing lead capture (schema + state only)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.contact import Contact
from app.persistence.models.lead import Lead
from app.persistence.repositories.contact_repository import ContactRepository
from app.persistence.repositories.lead_repository import LeadRepository


class LeadService:
    """Service for lead management (schema + state only, no Twilio/Zapier logic)."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize lead service."""
        self.session = session
        self.lead_repo = LeadRepository(session)
        self.contact_repo = ContactRepository(session)

    async def capture_lead(
        self,
        tenant_id: int,
        conversation_id: int | None = None,
        email: str | None = None,
        phone: str | None = None,
        name: str | None = None,
        metadata: dict | None = None,
    ) -> Lead:
        """Capture a lead (create lead record).

        Args:
            tenant_id: Tenant ID
            conversation_id: Optional conversation ID
            email: Optional email
            phone: Optional phone
            name: Optional name
            metadata: Optional metadata dictionary (mapped to extra_data)

        Returns:
            Created lead
        """
        lead = await self.lead_repo.create(
            tenant_id,
            conversation_id=conversation_id,
            email=email,
            phone=phone,
            name=name,
            extra_data=metadata,  # Map metadata parameter to extra_data field
        )
        return lead

    async def get_lead(self, tenant_id: int, lead_id: int) -> Lead | None:
        """Get a lead by ID.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            Lead or None if not found
        """
        return await self.lead_repo.get_by_id(tenant_id, lead_id)

    async def list_leads(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[Lead]:
        """List leads for a tenant.

        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of leads
        """
        return await self.lead_repo.list(tenant_id, skip=skip, limit=limit)

    async def get_lead_by_conversation(
        self, tenant_id: int, conversation_id: int
    ) -> Lead | None:
        """Get lead by conversation ID.

        Args:
            tenant_id: Tenant ID
            conversation_id: Conversation ID

        Returns:
            Lead or None if not found
        """
        return await self.lead_repo.get_by_conversation(tenant_id, conversation_id)

    async def update_lead_status(
        self, tenant_id: int, lead_id: int, status: str
    ) -> Lead | None:
        """Update lead status and create Contact if verified.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID
            status: New status ('new', 'verified', 'unknown')

        Returns:
            Updated lead or None if not found
        """
        lead = await self.lead_repo.get_by_id(tenant_id, lead_id)
        if not lead:
            return None
        
        lead.status = status
        
        # If verified, create a Contact record if one doesn't exist
        if status == 'verified':
            await self._create_contact_from_lead(tenant_id, lead)
        
        await self.session.commit()
        await self.session.refresh(lead)
        return lead

    async def _create_contact_from_lead(self, tenant_id: int, lead: Lead) -> Contact | None:
        """Create a Contact from a verified lead if one doesn't already exist.

        Args:
            tenant_id: Tenant ID
            lead: Lead to create contact from

        Returns:
            Created Contact or None if contact already exists
        """
        # Check if a contact already exists with this email or phone
        existing_contact = await self.contact_repo.get_by_email_or_phone(
            tenant_id, email=lead.email, phone=lead.phone
        )
        
        if existing_contact:
            return None
        
        # Create new contact from lead data
        contact = Contact(
            tenant_id=tenant_id,
            email=lead.email,
            phone=lead.phone,
            name=lead.name,
            source='web_chat_lead',
        )
        self.session.add(contact)
        return contact

    async def delete_lead(self, tenant_id: int, lead_id: int) -> bool:
        """Delete a lead by ID.
        
        Before deleting, nullifies any contact's lead_id that references this lead
        to prevent foreign key constraint violations.
        
        Uses raw SQL to avoid ORM relationship loading which would query
        non-existent columns in the Contact model.

        Args:
            tenant_id: Tenant ID
            lead_id: Lead ID

        Returns:
            True if deleted, False if not found
        """
        # First, check if lead exists using raw SQL to avoid relationship loading
        result = await self.session.execute(
            text("SELECT id FROM leads WHERE id = :lead_id AND tenant_id = :tenant_id"),
            {"lead_id": lead_id, "tenant_id": tenant_id}
        )
        if result.scalar_one_or_none() is None:
            return False
        
        # Nullify any contact's lead_id that references this lead using raw SQL
        await self.session.execute(
            text("UPDATE contacts SET lead_id = NULL WHERE tenant_id = :tenant_id AND lead_id = :lead_id"),
            {"tenant_id": tenant_id, "lead_id": lead_id}
        )
        
        # Delete the lead using raw SQL to avoid relationship loading
        await self.session.execute(
            text("DELETE FROM leads WHERE id = :lead_id AND tenant_id = :tenant_id"),
            {"lead_id": lead_id, "tenant_id": tenant_id}
        )
        
        await self.session.commit()
        return True
