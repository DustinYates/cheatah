"""Contact alias repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.persistence.models.contact_alias import ContactAlias
from app.persistence.repositories.base import BaseRepository


class ContactAliasRepository(BaseRepository[ContactAlias]):
    """Repository for ContactAlias entities."""

    def __init__(self, session: AsyncSession):
        """Initialize contact alias repository."""
        super().__init__(ContactAlias, session)

    async def get_aliases_for_contact(self, contact_id: int) -> list[ContactAlias]:
        """Get all aliases for a contact.
        
        Args:
            contact_id: Contact ID
            
        Returns:
            List of aliases
        """
        stmt = (
            select(ContactAlias)
            .where(ContactAlias.contact_id == contact_id)
            .order_by(ContactAlias.is_primary.desc(), ContactAlias.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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
        stmt = (
            select(ContactAlias)
            .where(
                ContactAlias.contact_id == contact_id,
                ContactAlias.alias_type == alias_type
            )
            .order_by(ContactAlias.is_primary.desc(), ContactAlias.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_alias(
        self,
        contact_id: int,
        alias_type: str,
        value: str,
        is_primary: bool = False,
        source_contact_id: int | None = None
    ) -> ContactAlias:
        """Create a new alias for a contact.
        
        Args:
            contact_id: Contact ID
            alias_type: Type of alias ('email', 'phone', 'name')
            value: The alias value
            is_primary: Whether this is the primary value
            source_contact_id: Original contact this came from (for merges)
            
        Returns:
            Created alias
        """
        alias = ContactAlias(
            contact_id=contact_id,
            alias_type=alias_type,
            value=value,
            is_primary=is_primary,
            source_contact_id=source_contact_id
        )
        self.session.add(alias)
        await self.session.commit()
        await self.session.refresh(alias)
        return alias

    async def create_aliases_bulk(self, aliases: list[dict]) -> list[ContactAlias]:
        """Create multiple aliases at once.
        
        Args:
            aliases: List of alias data dicts with keys:
                     contact_id, alias_type, value, is_primary, source_contact_id
            
        Returns:
            List of created aliases
        """
        created = []
        for alias_data in aliases:
            alias = ContactAlias(**alias_data)
            self.session.add(alias)
            created.append(alias)
        
        await self.session.commit()
        
        # Refresh aliases if possible, but don't fail if session is in bad state
        for alias in created:
            try:
                await self.session.refresh(alias)
            except Exception:
                # If refresh fails, continue - aliases are already committed
                pass
        
        return created

    async def set_primary(
        self, contact_id: int, alias_type: str, alias_id: int
    ) -> ContactAlias | None:
        """Set a specific alias as primary for its type.
        
        Args:
            contact_id: Contact ID
            alias_type: Type of alias
            alias_id: Alias ID to make primary
            
        Returns:
            Updated alias or None if not found
        """
        # First, unset all primaries of this type
        stmt = select(ContactAlias).where(
            ContactAlias.contact_id == contact_id,
            ContactAlias.alias_type == alias_type
        )
        result = await self.session.execute(stmt)
        aliases = result.scalars().all()
        
        target_alias = None
        for alias in aliases:
            if alias.id == alias_id:
                alias.is_primary = True
                target_alias = alias
            else:
                alias.is_primary = False
        
        await self.session.commit()
        
        if target_alias:
            await self.session.refresh(target_alias)
        
        return target_alias

    async def delete_alias(self, alias_id: int) -> bool:
        """Delete an alias.
        
        Args:
            alias_id: Alias ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        stmt = select(ContactAlias).where(ContactAlias.id == alias_id)
        result = await self.session.execute(stmt)
        alias = result.scalar_one_or_none()
        
        if not alias:
            return False
        
        await self.session.delete(alias)
        await self.session.commit()
        return True

    async def find_by_value(
        self, alias_type: str, value: str
    ) -> list[ContactAlias]:
        """Find aliases by type and value across all contacts.
        
        Args:
            alias_type: Type of alias
            value: Value to search for
            
        Returns:
            List of matching aliases
        """
        stmt = select(ContactAlias).where(
            ContactAlias.alias_type == alias_type,
            ContactAlias.value == value
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
