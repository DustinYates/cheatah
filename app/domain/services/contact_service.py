"""Contact service for managing contacts."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.contact import Contact
from app.persistence.models.contact_alias import ContactAlias
from app.persistence.repositories.contact_repository import ContactRepository
from app.persistence.repositories.contact_alias_repository import ContactAliasRepository


class ContactService:
    """Service for contact management."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize contact service."""
        self.session = session
        self.contact_repo = ContactRepository(session)
        self.alias_repo = ContactAliasRepository(session)

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

    async def get_contact_with_aliases(
        self, tenant_id: int, contact_id: int
    ) -> Contact | None:
        """Get a contact by ID with all aliases loaded.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID

        Returns:
            Contact with aliases or None if not found
        """
        return await self.contact_repo.get_by_id_with_aliases(tenant_id, contact_id)

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

    async def update_contact(
        self,
        tenant_id: int,
        contact_id: int,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None
    ) -> Contact | None:
        """Update a contact's fields.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            name: New name (optional)
            email: New email (optional)
            phone: New phone (optional)

        Returns:
            Updated contact or None if not found
        """
        return await self.contact_repo.update_contact(
            tenant_id, contact_id, name=name, email=email, phone=phone
        )

    async def delete_contact(self, tenant_id: int, contact_id: int) -> bool:
        """Permanently delete a contact.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID

        Returns:
            True if deleted, False if not found
        """
        return await self.contact_repo.hard_delete(tenant_id, contact_id)

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

    # Alias management methods
    
    async def get_aliases(self, contact_id: int) -> list[ContactAlias]:
        """Get all aliases for a contact.

        Args:
            contact_id: Contact ID

        Returns:
            List of aliases
        """
        return await self.alias_repo.get_aliases_for_contact(contact_id)

    async def get_aliases_by_type(
        self, contact_id: int, alias_type: str
    ) -> list[ContactAlias]:
        """Get aliases of a specific type for a contact.

        Args:
            contact_id: Contact ID
            alias_type: Type of alias ('email', 'phone', 'name')

        Returns:
            List of aliases of that type
        """
        return await self.alias_repo.get_aliases_by_type(contact_id, alias_type)

    async def add_alias(
        self,
        tenant_id: int,
        contact_id: int,
        alias_type: str,
        value: str,
        is_primary: bool = False
    ) -> ContactAlias | None:
        """Add an alias to a contact.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            alias_type: Type of alias ('email', 'phone', 'name')
            value: The alias value
            is_primary: Whether this should be the primary value

        Returns:
            Created alias or None if contact not found
        """
        # Verify contact exists
        contact = await self.contact_repo.get_by_id(tenant_id, contact_id)
        if not contact:
            return None
            
        # If setting as primary, update contact's main field too
        if is_primary:
            await self._update_primary_field(tenant_id, contact_id, alias_type, value)
            # Unset other primaries of this type
            existing_aliases = await self.alias_repo.get_aliases_by_type(contact_id, alias_type)
            for alias in existing_aliases:
                if alias.is_primary:
                    alias.is_primary = False
            await self.session.commit()
            
        return await self.alias_repo.create_alias(
            contact_id=contact_id,
            alias_type=alias_type,
            value=value,
            is_primary=is_primary
        )

    async def remove_alias(
        self, tenant_id: int, contact_id: int, alias_id: int
    ) -> bool:
        """Remove an alias from a contact.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            alias_id: Alias ID to remove

        Returns:
            True if removed, False if not found or is primary
        """
        # Verify contact exists
        contact = await self.contact_repo.get_by_id(tenant_id, contact_id)
        if not contact:
            return False
            
        # Get the alias and verify it belongs to this contact
        aliases = await self.alias_repo.get_aliases_for_contact(contact_id)
        target_alias = None
        for alias in aliases:
            if alias.id == alias_id:
                target_alias = alias
                break
                
        if not target_alias:
            return False
            
        # Don't allow removing primary aliases
        if target_alias.is_primary:
            return False
            
        return await self.alias_repo.delete_alias(alias_id)

    async def set_primary_alias(
        self, tenant_id: int, contact_id: int, alias_id: int
    ) -> ContactAlias | None:
        """Set an alias as the primary for its type.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            alias_id: Alias ID to set as primary

        Returns:
            Updated alias or None if not found
        """
        # Verify contact exists
        contact = await self.contact_repo.get_by_id(tenant_id, contact_id)
        if not contact:
            return None
            
        # Get the alias to find its type
        aliases = await self.alias_repo.get_aliases_for_contact(contact_id)
        target_alias = None
        for alias in aliases:
            if alias.id == alias_id:
                target_alias = alias
                break
                
        if not target_alias:
            return None
            
        # Set as primary in the alias table
        result = await self.alias_repo.set_primary(
            contact_id, target_alias.alias_type, alias_id
        )
        
        # Update the contact's main field
        if result:
            await self._update_primary_field(
                tenant_id, contact_id, target_alias.alias_type, target_alias.value
            )
            
        return result

    async def _update_primary_field(
        self,
        tenant_id: int,
        contact_id: int,
        alias_type: str,
        value: str
    ) -> None:
        """Update the contact's primary field based on alias type.

        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            alias_type: Type of alias ('email', 'phone', 'name')
            value: The value to set
        """
        if alias_type == 'email':
            await self.contact_repo.update_contact(tenant_id, contact_id, email=value)
        elif alias_type == 'phone':
            await self.contact_repo.update_contact(tenant_id, contact_id, phone=value)
        elif alias_type == 'name':
            await self.contact_repo.update_contact(tenant_id, contact_id, name=value)

