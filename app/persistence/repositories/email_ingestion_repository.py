"""Repository for EmailIngestionLog entities."""

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.email_ingestion_log import EmailIngestionLog, IngestionStatus
from app.persistence.repositories.base import BaseRepository


class EmailIngestionLogRepository(BaseRepository[EmailIngestionLog]):
    """Repository for EmailIngestionLog entities.

    Handles deduplication, status updates, and audit trail for SendGrid Inbound Parse.
    """

    def __init__(self, session: AsyncSession):
        """Initialize email ingestion log repository."""
        super().__init__(EmailIngestionLog, session)

    async def create(
        self,
        tenant_id: int,
        message_id: str,
        from_email: str,
        **kwargs: Any,
    ) -> EmailIngestionLog:
        """Create new ingestion log entry.

        Note: This may raise IntegrityError if a duplicate message_id exists,
        which is the expected deduplication behavior.

        Args:
            tenant_id: Tenant ID
            message_id: RFC 2822 Message-ID or hash fallback
            from_email: Sender email address
            **kwargs: Additional fields (to_email, subject, raw_payload, etc.)

        Returns:
            Created EmailIngestionLog

        Raises:
            IntegrityError: If duplicate message_id for tenant (expected for dedup)
        """
        log = EmailIngestionLog(
            tenant_id=tenant_id,
            message_id=message_id,
            from_email=from_email,
            **kwargs,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        return log

    async def get_by_id(self, log_id: int) -> EmailIngestionLog | None:
        """Get ingestion log by ID (for async processing).

        Args:
            log_id: Ingestion log ID

        Returns:
            EmailIngestionLog or None
        """
        stmt = select(EmailIngestionLog).where(EmailIngestionLog.id == log_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_message_id(
        self, tenant_id: int, message_id: str
    ) -> EmailIngestionLog | None:
        """Get ingestion log by message ID (for deduplication check).

        Args:
            tenant_id: Tenant ID
            message_id: RFC 2822 Message-ID or hash

        Returns:
            EmailIngestionLog or None
        """
        stmt = select(EmailIngestionLog).where(
            EmailIngestionLog.tenant_id == tenant_id,
            EmailIngestionLog.message_id == message_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        log_id: int,
        status: str | IngestionStatus,
        error_message: str | None = None,
        lead_id: int | None = None,
    ) -> bool:
        """Update ingestion log status after processing.

        Args:
            log_id: Ingestion log ID
            status: New status (received/processed/failed/duplicate/skipped)
            error_message: Optional error message for failed status
            lead_id: Optional lead ID for processed status

        Returns:
            True if updated successfully
        """
        if isinstance(status, IngestionStatus):
            status = status.value

        update_data: dict[str, Any] = {"status": status}
        if error_message is not None:
            update_data["error_message"] = error_message
        if lead_id is not None:
            update_data["lead_id"] = lead_id

        stmt = (
            update(EmailIngestionLog)
            .where(EmailIngestionLog.id == log_id)
            .values(**update_data)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def list_failed(
        self, tenant_id: int, limit: int = 100
    ) -> list[EmailIngestionLog]:
        """List failed ingestion logs for retry/investigation.

        Args:
            tenant_id: Tenant ID
            limit: Maximum number of records to return

        Returns:
            List of failed EmailIngestionLog entries
        """
        stmt = (
            select(EmailIngestionLog)
            .where(
                EmailIngestionLog.tenant_id == tenant_id,
                EmailIngestionLog.status == IngestionStatus.FAILED.value,
            )
            .order_by(EmailIngestionLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant(
        self,
        tenant_id: int,
        status: str | IngestionStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[EmailIngestionLog]:
        """List ingestion logs for a tenant with optional status filter.

        Args:
            tenant_id: Tenant ID
            status: Optional status filter
            skip: Pagination offset
            limit: Pagination limit

        Returns:
            List of EmailIngestionLog entries
        """
        stmt = select(EmailIngestionLog).where(EmailIngestionLog.tenant_id == tenant_id)

        if status is not None:
            if isinstance(status, IngestionStatus):
                status = status.value
            stmt = stmt.where(EmailIngestionLog.status == status)

        stmt = stmt.order_by(EmailIngestionLog.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_stats(self, tenant_id: int) -> dict[str, int]:
        """Get ingestion statistics for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with counts by status
        """
        from sqlalchemy import func

        stmt = (
            select(
                EmailIngestionLog.status,
                func.count(EmailIngestionLog.id).label("count"),
            )
            .where(EmailIngestionLog.tenant_id == tenant_id)
            .group_by(EmailIngestionLog.status)
        )
        result = await self.session.execute(stmt)

        stats = {status.value: 0 for status in IngestionStatus}
        for row in result:
            stats[row.status] = row.count

        return stats
