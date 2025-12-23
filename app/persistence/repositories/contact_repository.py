"""Contact repository."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload

from app.persistence.models.contact import Contact
from app.persistence.repositories.base import BaseRepository


class ContactRepository(BaseRepository[Contact]):
    """Repository for Contact entities."""

    def __init__(self, session: AsyncSession):
        """Initialize contact repository."""
        super().__init__(Contact, session)

    async def get_by_id(self, tenant_id: int, id: int) -> Contact | None:
        """Get active contact by ID (excludes deleted and merged).
        
        Args:
            tenant_id: Tenant ID
            id: Contact ID
            
        Returns:
            Contact or None if not found or inactive
        """
        stmt = select(Contact).where(
            Contact.id == id,
            Contact.tenant_id == tenant_id,
            Contact.deleted_at.is_(None),
            Contact.merged_into_contact_id.is_(None)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_any_status(self, tenant_id: int, id: int) -> Contact | None:
        """Get contact by ID regardless of status (includes deleted/merged).
        
        Args:
            tenant_id: Tenant ID
            id: Contact ID
            
        Returns:
            Contact or None if not found
        """
        stmt = select(Contact).where(
            Contact.id == id,
            Contact.tenant_id == tenant_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_aliases(self, tenant_id: int, id: int) -> Contact | None:
        """Get contact by ID with aliases loaded.
        
        Args:
            tenant_id: Tenant ID
            id: Contact ID
            
        Returns:
            Contact with aliases or None if not found
        """
        stmt = (
            select(Contact)
            .options(selectinload(Contact.aliases))
            .where(
                Contact.id == id,
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
                Contact.merged_into_contact_id.is_(None)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email_or_phone(
        self, tenant_id: int, email: str | None = None, phone: str | None = None
    ) -> Contact | None:
        """Get contact by email or phone.
        
        Returns the first matching contact if multiple exist (duplicates
        should be merged using the merge feature).
        
        Args:
            tenant_id: Tenant ID
            email: Optional email to search
            phone: Optional phone to search
            
        Returns:
            Contact or None if not found
        """
        if not email and not phone:
            return None
            
        conditions = []
        if email:
            conditions.append(Contact.email == email)
        if phone:
            conditions.append(Contact.phone == phone)
        
        stmt = (
            select(Contact)
            .where(
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
                Contact.merged_into_contact_id.is_(None),
                or_(*conditions)
            )
            .order_by(Contact.created_at)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[Contact]:
        """List active contacts for a tenant (excludes deleted and merged).
        
        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of contacts
        """
        stmt = (
            select(Contact)
            .where(
                Contact.tenant_id == tenant_id,
                Contact.deleted_at.is_(None),
                Contact.merged_into_contact_id.is_(None)
            )
            .order_by(Contact.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_multiple_by_ids(
        self, tenant_id: int, ids: list[int]
    ) -> list[Contact]:
        """Get multiple contacts by IDs.
        
        Args:
            tenant_id: Tenant ID
            ids: List of contact IDs
            
        Returns:
            List of contacts found
        """
        if not ids:
            return []
            
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.id.in_(ids),
            Contact.deleted_at.is_(None),
            Contact.merged_into_contact_id.is_(None)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_merged(
        self,
        tenant_id: int,
        contact_id: int,
        merged_into_id: int,
        user_id: int
    ) -> Contact | None:
        """Mark a contact as merged into another contact.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID to mark as merged
            merged_into_id: Contact ID it was merged into
            user_id: User performing the merge
            
        Returns:
            Updated contact or None if not found
        """
        contact = await self.get_by_id_any_status(tenant_id, contact_id)
        if not contact:
            return None
            
        contact.merged_into_contact_id = merged_into_id
        contact.merged_at = datetime.utcnow()
        contact.merged_by = user_id
        
        await self.session.commit()
        # Don't refresh if session is closed or object is detached
        try:
            await self.session.refresh(contact)
        except Exception:
            # If refresh fails, re-fetch the contact
            contact = await self.get_by_id_any_status(tenant_id, contact_id)
        return contact

    async def get_merged_contacts(
        self, tenant_id: int, primary_contact_id: int
    ) -> list[Contact]:
        """Get all contacts that were merged into a primary contact.
        
        Args:
            tenant_id: Tenant ID
            primary_contact_id: Primary contact ID
            
        Returns:
            List of contacts merged into the primary
        """
        stmt = select(Contact).where(
            Contact.tenant_id == tenant_id,
            Contact.merged_into_contact_id == primary_contact_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def hard_delete(self, tenant_id: int, contact_id: int) -> bool:
        """Permanently delete a contact and its aliases.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        contact = await self.get_by_id_any_status(tenant_id, contact_id)
        if not contact:
            return False
            
        await self.session.delete(contact)
        await self.session.commit()
        return True

    async def soft_delete(
        self, tenant_id: int, contact_id: int, user_id: int
    ) -> Contact | None:
        """Soft delete a contact (mark as deleted but preserve data).
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID to delete
            user_id: User performing the deletion
            
        Returns:
            Updated contact or None if not found
        """
        contact = await self.get_by_id(tenant_id, contact_id)
        if not contact:
            return None
            
        contact.deleted_at = datetime.utcnow()
        contact.deleted_by = user_id
        
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

    async def update_contact(
        self,
        tenant_id: int,
        contact_id: int,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None
    ) -> Contact | None:
        """Update contact fields.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            name: New name (optional)
            email: New email (optional)
            phone: New phone (optional)
            
        Returns:
            Updated contact or None if not found
        """
        contact = await self.get_by_id(tenant_id, contact_id)
        if not contact:
            return None
            
        if name is not None:
            contact.name = name
        if email is not None:
            contact.email = email
        if phone is not None:
            contact.phone = phone
            
        await self.session.commit()
        await self.session.refresh(contact)
        return contact

