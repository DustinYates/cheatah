"""Repository for Zapier request tracking."""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.zapier_request import ZapierRequest
from app.persistence.repositories.base import BaseRepository


class ZapierRequestRepository(BaseRepository[ZapierRequest]):
    """Repository for Zapier request correlation tracking."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(ZapierRequest, session)

    async def get_by_correlation_id(self, correlation_id: str) -> ZapierRequest | None:
        """Get request by correlation ID.

        Args:
            correlation_id: Unique correlation ID

        Returns:
            Request or None if not found
        """
        stmt = select(ZapierRequest).where(
            ZapierRequest.correlation_id == correlation_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_requests(
        self,
        tenant_id: int,
        older_than_seconds: int = 60,
    ) -> list[ZapierRequest]:
        """Get pending requests older than threshold.

        Used for cleanup, retry logic, or timeout detection.

        Args:
            tenant_id: Tenant ID
            older_than_seconds: Age threshold in seconds

        Returns:
            List of pending requests older than threshold
        """
        cutoff = datetime.utcnow() - timedelta(seconds=older_than_seconds)
        stmt = select(ZapierRequest).where(
            ZapierRequest.tenant_id == tenant_id,
            ZapierRequest.status == "pending",
            ZapierRequest.request_sent_at < cutoff,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_with_response(
        self,
        correlation_id: str,
        response_payload: dict,
        status: str = "completed",
        error_message: str | None = None,
    ) -> ZapierRequest | None:
        """Update request with response from Zapier callback.

        Args:
            correlation_id: Request correlation ID
            response_payload: Response payload from Zapier
            status: New status (completed, error, etc.)
            error_message: Optional error message

        Returns:
            Updated request or None if not found
        """
        request = await self.get_by_correlation_id(correlation_id)
        if not request:
            return None

        request.response_payload = response_payload
        request.response_received_at = datetime.utcnow()
        request.status = status
        if error_message:
            request.error_message = error_message

        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def mark_timeout(self, correlation_id: str) -> ZapierRequest | None:
        """Mark a request as timed out.

        Args:
            correlation_id: Request correlation ID

        Returns:
            Updated request or None if not found
        """
        request = await self.get_by_correlation_id(correlation_id)
        if not request:
            return None

        request.status = "timeout"
        request.error_message = "Request timed out waiting for Zapier callback"

        await self.session.commit()
        await self.session.refresh(request)
        return request

    async def get_by_phone_number(
        self,
        tenant_id: int,
        phone_number: str,
        request_type: str | None = None,
        limit: int = 10,
    ) -> list[ZapierRequest]:
        """Get requests by phone number.

        Args:
            tenant_id: Tenant ID
            phone_number: Phone number to search
            request_type: Optional filter by request type
            limit: Maximum number of results

        Returns:
            List of requests
        """
        stmt = select(ZapierRequest).where(
            ZapierRequest.tenant_id == tenant_id,
            ZapierRequest.phone_number == phone_number,
        )

        if request_type:
            stmt = stmt.where(ZapierRequest.request_type == request_type)

        stmt = stmt.order_by(ZapierRequest.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
