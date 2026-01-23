"""Do Not Contact repository."""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.do_not_contact import DoNotContact
from app.persistence.repositories.base import BaseRepository


class DncRepository(BaseRepository[DoNotContact]):
    """Repository for DoNotContact entities."""

    def __init__(self, session: AsyncSession):
        """Initialize DNC repository."""
        super().__init__(DoNotContact, session)

    async def get_active_by_phone_or_email(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
    ) -> DoNotContact | None:
        """Get active DNC record by phone or email.

        Args:
            tenant_id: Tenant ID
            phone: Phone number (optional)
            email: Email address (optional)

        Returns:
            Active DNC record or None if not blocked
        """
        if not phone and not email:
            return None

        conditions = [DoNotContact.tenant_id == tenant_id, DoNotContact.is_active == True]

        identifier_conditions = []
        if phone:
            identifier_conditions.append(DoNotContact.phone_number == phone)
        if email:
            identifier_conditions.append(DoNotContact.email == email)

        if identifier_conditions:
            conditions.append(or_(*identifier_conditions))

        stmt = select(DoNotContact).where(*conditions)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def is_blocked(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
    ) -> bool:
        """Check if phone or email is on active DNC list.

        Args:
            tenant_id: Tenant ID
            phone: Phone number (optional)
            email: Email address (optional)

        Returns:
            True if blocked, False otherwise
        """
        record = await self.get_active_by_phone_or_email(tenant_id, phone, email)
        return record is not None

    async def create_dnc(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
        source_channel: str = "manual",
        source_message: str | None = None,
        source_conversation_id: int | None = None,
        created_by: int | None = None,
    ) -> DoNotContact:
        """Create a new DNC record.

        Args:
            tenant_id: Tenant ID
            phone: Phone number (optional)
            email: Email address (optional)
            source_channel: How DNC was triggered ("sms", "email", "voice", "manual")
            source_message: The message that triggered DNC
            source_conversation_id: Conversation ID if applicable
            created_by: User ID who created the record (None if auto-detected)

        Returns:
            Created DNC record
        """
        # Check if already blocked
        existing = await self.get_active_by_phone_or_email(tenant_id, phone, email)
        if existing:
            return existing

        record = DoNotContact(
            tenant_id=tenant_id,
            phone_number=phone,
            email=email,
            is_active=True,
            source_channel=source_channel,
            source_message=source_message,
            source_conversation_id=source_conversation_id,
            created_by=created_by,
            created_at=datetime.utcnow(),
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def deactivate(
        self,
        tenant_id: int,
        phone: str | None = None,
        email: str | None = None,
        deactivated_by: int | None = None,
        reason: str | None = None,
    ) -> bool:
        """Deactivate (unblock) a DNC record.

        Args:
            tenant_id: Tenant ID
            phone: Phone number (optional)
            email: Email address (optional)
            deactivated_by: User ID who deactivated
            reason: Reason for deactivation

        Returns:
            True if deactivated, False if not found
        """
        record = await self.get_active_by_phone_or_email(tenant_id, phone, email)
        if not record:
            return False

        record.is_active = False
        record.deactivated_at = datetime.utcnow()
        record.deactivated_by = deactivated_by
        record.deactivation_reason = reason

        await self.session.commit()
        return True

    async def list_active(
        self,
        tenant_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[DoNotContact]:
        """List all active DNC records for a tenant.

        Args:
            tenant_id: Tenant ID
            skip: Number of records to skip
            limit: Maximum records to return

        Returns:
            List of active DNC records
        """
        stmt = (
            select(DoNotContact)
            .where(DoNotContact.tenant_id == tenant_id, DoNotContact.is_active == True)
            .order_by(DoNotContact.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_active(self, tenant_id: int) -> int:
        """Count active DNC records for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Count of active DNC records
        """
        from sqlalchemy import func

        stmt = select(func.count(DoNotContact.id)).where(
            DoNotContact.tenant_id == tenant_id, DoNotContact.is_active == True
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
