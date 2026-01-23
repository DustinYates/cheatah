"""Do Not Contact (DNC) service for opt-out management."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.do_not_contact import DoNotContact
from app.persistence.repositories.dnc_repository import DncRepository

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DncService:
    """Service for managing Do Not Contact status.

    This service handles blocking and unblocking contacts from
    receiving automated communications (SMS, email, etc.).
    """

    def __init__(self, session: AsyncSession):
        """Initialize DNC service.

        Args:
            session: Database session
        """
        self.session = session
        self.repository = DncRepository(session)

    async def is_blocked(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
    ) -> bool:
        """Check if a phone or email is on the DNC list.

        Args:
            tenant_id: Tenant ID
            phone: Phone number to check
            email: Email address to check

        Returns:
            True if blocked, False otherwise
        """
        if not phone and not email:
            return False

        is_blocked = await self.repository.is_blocked(tenant_id, phone, email)

        if is_blocked:
            identifier = phone or email
            logger.info(f"DNC check: BLOCKED - tenant_id={tenant_id}, identifier={identifier}")

        return is_blocked

    async def block(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
        source_channel: str = "manual",
        source_message: str | None = None,
        source_conversation_id: int | None = None,
        created_by: int | None = None,
    ) -> DoNotContact:
        """Add a phone/email to the DNC list.

        Args:
            tenant_id: Tenant ID
            phone: Phone number to block
            email: Email to block
            source_channel: How DNC was triggered ("sms", "email", "voice", "manual")
            source_message: The message that triggered DNC (truncated to 500 chars)
            source_conversation_id: Conversation ID if applicable
            created_by: User ID who created the record (None if auto-detected)

        Returns:
            Created or existing DNC record

        Raises:
            ValueError: If neither phone nor email provided
        """
        if not phone and not email:
            raise ValueError("At least one of phone or email is required")

        # Truncate source message if too long
        if source_message and len(source_message) > 500:
            source_message = source_message[:497] + "..."

        record = await self.repository.create_dnc(
            tenant_id=tenant_id,
            phone=phone,
            email=email,
            source_channel=source_channel,
            source_message=source_message,
            source_conversation_id=source_conversation_id,
            created_by=created_by,
        )

        identifier = phone or email
        logger.info(
            f"DNC block: Added to list - tenant_id={tenant_id}, "
            f"identifier={identifier}, source={source_channel}, "
            f"created_by={'auto' if created_by is None else created_by}"
        )

        return record

    async def unblock(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
        deactivated_by: int | None = None,
        reason: str | None = None,
    ) -> bool:
        """Remove a phone/email from the DNC list.

        Args:
            tenant_id: Tenant ID
            phone: Phone number to unblock
            email: Email to unblock
            deactivated_by: User ID who is unblocking
            reason: Reason for unblocking

        Returns:
            True if unblocked, False if not found
        """
        success = await self.repository.deactivate(
            tenant_id=tenant_id,
            phone=phone,
            email=email,
            deactivated_by=deactivated_by,
            reason=reason,
        )

        identifier = phone or email
        if success:
            logger.info(
                f"DNC unblock: Removed from list - tenant_id={tenant_id}, "
                f"identifier={identifier}, reason={reason}"
            )
        else:
            logger.warning(
                f"DNC unblock: Not found - tenant_id={tenant_id}, identifier={identifier}"
            )

        return success

    async def get_record(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
    ) -> DoNotContact | None:
        """Get the active DNC record for a phone/email.

        Args:
            tenant_id: Tenant ID
            phone: Phone number
            email: Email address

        Returns:
            Active DNC record or None
        """
        return await self.repository.get_active_by_phone_or_email(tenant_id, phone, email)

    async def list_blocked(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DoNotContact]:
        """List all blocked contacts for a tenant.

        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of active DNC records
        """
        return await self.repository.list_active(tenant_id, skip, limit)

    async def count_blocked(self, tenant_id: int) -> int:
        """Count blocked contacts for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Count of active DNC records
        """
        return await self.repository.count_active(tenant_id)
