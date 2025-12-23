"""Contact merge log repository."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.persistence.models.contact_merge_log import ContactMergeLog
from app.persistence.repositories.base import BaseRepository


class ContactMergeLogRepository(BaseRepository[ContactMergeLog]):
    """Repository for ContactMergeLog entities."""

    def __init__(self, session: AsyncSession):
        """Initialize contact merge log repository."""
        super().__init__(ContactMergeLog, session)

    async def create_merge_log(
        self,
        tenant_id: int,
        primary_contact_id: int,
        secondary_contact_id: int,
        merged_by: int,
        field_resolutions: dict | None = None,
        secondary_data_snapshot: dict | None = None
    ) -> ContactMergeLog:
        """Create a merge log entry.
        
        Args:
            tenant_id: Tenant ID
            primary_contact_id: ID of the primary (surviving) contact
            secondary_contact_id: ID of the secondary (merged) contact
            merged_by: User ID who performed the merge
            field_resolutions: Dict of which fields came from which contact
            secondary_data_snapshot: Backup of secondary contact's data
            
        Returns:
            Created merge log
        """
        merge_log = ContactMergeLog(
            tenant_id=tenant_id,
            primary_contact_id=primary_contact_id,
            secondary_contact_id=secondary_contact_id,
            merged_by=merged_by,
            field_resolutions=field_resolutions,
            secondary_data_snapshot=secondary_data_snapshot
        )
        self.session.add(merge_log)
        await self.session.commit()
        # Don't refresh if session is closed or object is detached
        try:
            await self.session.refresh(merge_log)
        except Exception:
            # If refresh fails, that's okay - the log is already committed
            pass
        return merge_log

    async def get_merge_history_for_contact(
        self, tenant_id: int, contact_id: int
    ) -> list[ContactMergeLog]:
        """Get all merge logs where this contact was the primary.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID to get history for
            
        Returns:
            List of merge logs
        """
        stmt = (
            select(ContactMergeLog)
            .options(
                selectinload(ContactMergeLog.secondary_contact),
                selectinload(ContactMergeLog.user)
            )
            .where(
                ContactMergeLog.tenant_id == tenant_id,
                ContactMergeLog.primary_contact_id == contact_id
            )
            .order_by(ContactMergeLog.merged_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_merge_logs_for_tenant(
        self, tenant_id: int, skip: int = 0, limit: int = 100
    ) -> list[ContactMergeLog]:
        """Get all merge logs for a tenant.
        
        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum records to return
            
        Returns:
            List of merge logs
        """
        stmt = (
            select(ContactMergeLog)
            .options(
                selectinload(ContactMergeLog.primary_contact),
                selectinload(ContactMergeLog.secondary_contact),
                selectinload(ContactMergeLog.user)
            )
            .where(ContactMergeLog.tenant_id == tenant_id)
            .order_by(ContactMergeLog.merged_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def was_contact_merged(
        self, tenant_id: int, contact_id: int
    ) -> ContactMergeLog | None:
        """Check if a contact was merged as a secondary.
        
        Args:
            tenant_id: Tenant ID
            contact_id: Contact ID to check
            
        Returns:
            Merge log if found, None otherwise
        """
        stmt = (
            select(ContactMergeLog)
            .where(
                ContactMergeLog.tenant_id == tenant_id,
                ContactMergeLog.secondary_contact_id == contact_id
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
