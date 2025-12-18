"""Contact service for managing contacts."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.contact import Contact
from app.persistence.repositories.contact_repository import ContactRepository


class ContactService:
    """Service for contact management."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize contact service."""
        self.session = session
        self.contact_repo = ContactRepository(session)

    async def list_contacts(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[Contact]:
        """List contacts for a tenant.

        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of contacts
        """
        return await self.contact_repo.list_by_tenant(tenant_id, skip=skip, limit=limit)

    async def get_contact(self, tenant_id: int, contact_id: int) -> Contact | None:
        """Get a contact by ID.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID

        Returns:
            Contact or None if not found
        """
        return await self.contact_repo.get_by_id(tenant_id, contact_id)

    async def create_contact(
        self,
        tenant_id: int,
        email: str | None = None,
        phone: str | None = None,
        name: str | None = None,
        source: str | None = None,
    ) -> Contact:
        """Create a new contact.

        Args:
            tenant_id: Tenant ID
            email: Optional email
            phone: Optional phone
            name: Optional name
            source: Source of the contact (e.g., 'web_chat_lead', 'sms_optin')

        Returns:
            Created contact
        """
        return await self.contact_repo.create(
            tenant_id,
            email=email,
            phone=phone,
            name=name,
            source=source,
        )

    async def get_by_email_or_phone(
        self, tenant_id: int, email: str | None = None, phone: str | None = None
    ) -> Contact | None:
        """Get contact by email or phone.

        Args:
            tenant_id: Tenant ID
            email: Optional email to search
            phone: Optional phone to search

        Returns:
            Contact or None if not found
        """
        return await self.contact_repo.get_by_email_or_phone(tenant_id, email, phone)

