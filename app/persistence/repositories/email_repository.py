"""Email-related repositories for tenant config and email conversations."""

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant_email_config import EmailConversation, TenantEmailConfig
from app.persistence.repositories.base import BaseRepository


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    """Convert a datetime to naive UTC for database storage.
    
    asyncpg requires consistent datetime types - either all naive or all aware.
    Our database columns are timezone-naive, so we strip timezone info.
    
    Args:
        dt: A datetime that may be timezone-aware or naive
        
    Returns:
        A timezone-naive datetime, or None if input is None
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Remove timezone info (assumes input is already in UTC)
        return dt.replace(tzinfo=None)
    return dt


class TenantEmailConfigRepository(BaseRepository[TenantEmailConfig]):
    """Repository for TenantEmailConfig entities."""

    def __init__(self, session: AsyncSession):
        """Initialize tenant email config repository."""
        super().__init__(TenantEmailConfig, session)

    async def get_by_tenant_id(self, tenant_id: int) -> TenantEmailConfig | None:
        """Get email config for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            TenantEmailConfig or None
        """
        stmt = select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> TenantEmailConfig | None:
        """Get email config by Gmail address.
        
        Args:
            email: Gmail email address
            
        Returns:
            TenantEmailConfig or None
        """
        stmt = select(TenantEmailConfig).where(TenantEmailConfig.gmail_email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        tenant_id: int,
        **kwargs: Any,
    ) -> TenantEmailConfig:
        """Create or update email config for a tenant.
        
        Args:
            tenant_id: Tenant ID
            **kwargs: Config fields to update
            
        Returns:
            Created or updated TenantEmailConfig
        """
        existing = await self.get_by_tenant_id(tenant_id)
        
        if existing:
            # Update existing config
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    # Convert datetime values to naive UTC for database compatibility
                    if isinstance(value, datetime):
                        value = _to_naive_utc(value)
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        else:
            # Create new config - convert datetime values to naive UTC
            sanitized_kwargs = {}
            for key, value in kwargs.items():
                if isinstance(value, datetime):
                    sanitized_kwargs[key] = _to_naive_utc(value)
                else:
                    sanitized_kwargs[key] = value
            config = TenantEmailConfig(tenant_id=tenant_id, **sanitized_kwargs)
            self.session.add(config)
            await self.session.commit()
            await self.session.refresh(config)
            return config

    async def update_tokens(
        self,
        tenant_id: int,
        access_token: str,
        token_expires_at: datetime,
        refresh_token: str | None = None,
    ) -> bool:
        """Update OAuth tokens for a tenant.
        
        Args:
            tenant_id: Tenant ID
            access_token: New access token
            token_expires_at: Token expiration time
            refresh_token: Optional new refresh token
            
        Returns:
            True if updated successfully
        """
        update_data: dict[str, Any] = {
            "gmail_access_token": access_token,
            "gmail_token_expires_at": _to_naive_utc(token_expires_at),
            "updated_at": datetime.utcnow(),
        }
        if refresh_token:
            update_data["gmail_refresh_token"] = refresh_token
        
        stmt = (
            update(TenantEmailConfig)
            .where(TenantEmailConfig.tenant_id == tenant_id)
            .values(**update_data)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def update_history_id(
        self,
        tenant_id: int,
        history_id: str,
    ) -> bool:
        """Update Gmail history ID for incremental sync.
        
        Args:
            tenant_id: Tenant ID
            history_id: New history ID from Gmail API
            
        Returns:
            True if updated successfully
        """
        stmt = (
            update(TenantEmailConfig)
            .where(TenantEmailConfig.tenant_id == tenant_id)
            .values(last_history_id=history_id, updated_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def get_all_enabled(self) -> list[TenantEmailConfig]:
        """Get all enabled email configs (for watch refresh).

        Returns:
            List of enabled TenantEmailConfig
        """
        stmt = select(TenantEmailConfig).where(TenantEmailConfig.is_enabled == True)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_watch_expiration(
        self,
        tenant_id: int,
        watch_expiration: datetime,
        history_id: str | None = None,
    ) -> bool:
        """Update Gmail watch expiration for a tenant.

        Args:
            tenant_id: Tenant ID
            watch_expiration: New watch expiration time
            history_id: Optional new history ID

        Returns:
            True if updated successfully
        """
        update_data: dict[str, Any] = {
            "watch_expiration": _to_naive_utc(watch_expiration),
            "updated_at": datetime.utcnow(),
        }
        if history_id:
            update_data["last_history_id"] = history_id

        stmt = (
            update(TenantEmailConfig)
            .where(TenantEmailConfig.tenant_id == tenant_id)
            .values(**update_data)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0


class EmailConversationRepository(BaseRepository[EmailConversation]):
    """Repository for EmailConversation entities."""

    def __init__(self, session: AsyncSession):
        """Initialize email conversation repository."""
        super().__init__(EmailConversation, session)

    async def get_by_thread_id(
        self,
        tenant_id: int,
        gmail_thread_id: str,
    ) -> EmailConversation | None:
        """Get email conversation by Gmail thread ID.
        
        Args:
            tenant_id: Tenant ID
            gmail_thread_id: Gmail thread ID
            
        Returns:
            EmailConversation or None
        """
        stmt = select(EmailConversation).where(
            EmailConversation.tenant_id == tenant_id,
            EmailConversation.gmail_thread_id == gmail_thread_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_from_email(
        self,
        tenant_id: int,
        from_email: str,
        limit: int = 10,
    ) -> list[EmailConversation]:
        """Get email conversations from a specific sender.
        
        Args:
            tenant_id: Tenant ID
            from_email: Sender email address
            limit: Maximum results
            
        Returns:
            List of EmailConversation
        """
        stmt = (
            select(EmailConversation)
            .where(
                EmailConversation.tenant_id == tenant_id,
                EmailConversation.from_email == from_email,
            )
            .order_by(EmailConversation.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_or_update(
        self,
        tenant_id: int,
        gmail_thread_id: str,
        **kwargs: Any,
    ) -> EmailConversation:
        """Create or update email conversation.
        
        Args:
            tenant_id: Tenant ID
            gmail_thread_id: Gmail thread ID
            **kwargs: Conversation fields
            
        Returns:
            Created or updated EmailConversation
        """
        existing = await self.get_by_thread_id(tenant_id, gmail_thread_id)
        
        if existing:
            # Update existing
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            existing.message_count = existing.message_count + 1
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        else:
            # Create new
            conversation = EmailConversation(
                tenant_id=tenant_id,
                gmail_thread_id=gmail_thread_id,
                **kwargs,
            )
            self.session.add(conversation)
            await self.session.commit()
            await self.session.refresh(conversation)
            return conversation

    async def list_by_tenant(
        self,
        tenant_id: int,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[EmailConversation]:
        """List email conversations for a tenant.
        
        Args:
            tenant_id: Tenant ID
            status: Optional status filter
            skip: Pagination offset
            limit: Pagination limit
            
        Returns:
            List of EmailConversation
        """
        stmt = select(EmailConversation).where(EmailConversation.tenant_id == tenant_id)
        
        if status:
            stmt = stmt.where(EmailConversation.status == status)
        
        stmt = stmt.order_by(EmailConversation.updated_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_contact(
        self,
        tenant_id: int,
        contact_id: int,
        skip: int = 0,
        limit: int = 50,
    ) -> list[EmailConversation]:
        """List email conversations for a specific contact.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID
            skip: Pagination offset
            limit: Pagination limit
            
        Returns:
            List of EmailConversation
        """
        stmt = (
            select(EmailConversation)
            .where(
                EmailConversation.tenant_id == tenant_id,
                EmailConversation.contact_id == contact_id,
            )
            .order_by(EmailConversation.updated_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        tenant_id: int,
        gmail_thread_id: str,
        status: str,
    ) -> bool:
        """Update conversation status.
        
        Args:
            tenant_id: Tenant ID
            gmail_thread_id: Gmail thread ID
            status: New status
            
        Returns:
            True if updated successfully
        """
        stmt = (
            update(EmailConversation)
            .where(
                EmailConversation.tenant_id == tenant_id,
                EmailConversation.gmail_thread_id == gmail_thread_id,
            )
            .values(status=status, updated_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def link_to_contact(
        self,
        tenant_id: int,
        gmail_thread_id: str,
        contact_id: int | None = None,
        lead_id: int | None = None,
    ) -> bool:
        """Link email conversation to a contact or lead.
        
        Args:
            tenant_id: Tenant ID
            gmail_thread_id: Gmail thread ID
            contact_id: Optional contact ID
            lead_id: Optional lead ID
            
        Returns:
            True if updated successfully
        """
        update_data: dict[str, Any] = {"updated_at": datetime.utcnow()}
        if contact_id is not None:
            update_data["contact_id"] = contact_id
        if lead_id is not None:
            update_data["lead_id"] = lead_id
        
        stmt = (
            update(EmailConversation)
            .where(
                EmailConversation.tenant_id == tenant_id,
                EmailConversation.gmail_thread_id == gmail_thread_id,
            )
            .values(**update_data)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

