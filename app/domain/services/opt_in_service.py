"""Opt-in service for tracking SMS opt-ins."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.sms_opt_in import SmsOptIn
from app.persistence.repositories.sms_opt_in_repository import SmsOptInRepository


class OptInService:
    """Service for managing SMS opt-ins."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize opt-in service."""
        self.session = session
        self.opt_in_repo = SmsOptInRepository(session)

    async def is_opted_in(self, tenant_id: int, phone_number: str) -> bool:
        """Check if phone number is opted in.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            
        Returns:
            True if opted in, False otherwise
        """
        opt_in = await self.opt_in_repo.get_by_phone(tenant_id, phone_number)
        return opt_in.is_opted_in if opt_in else False

    async def opt_in(
        self,
        tenant_id: int,
        phone_number: str,
        method: str = "keyword",
    ) -> SmsOptIn:
        """Opt in a phone number.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            method: Opt-in method (keyword, manual, api, etc.)
            
        Returns:
            Opt-in record
        """
        opt_in = await self.opt_in_repo.get_by_phone(tenant_id, phone_number)
        
        if opt_in:
            # Update existing record
            opt_in.is_opted_in = True
            opt_in.opted_in_at = datetime.utcnow()
            opt_in.opt_in_method = method
            opt_in.opted_out_at = None
            opt_in.opt_out_method = None
            await self.session.commit()
            await self.session.refresh(opt_in)
            return opt_in
        else:
            # Create new record
            return await self.opt_in_repo.create(
                tenant_id,
                phone_number=phone_number,
                is_opted_in=True,
                opted_in_at=datetime.utcnow(),
                opt_in_method=method,
            )

    async def opt_out(
        self,
        tenant_id: int,
        phone_number: str,
        method: str = "STOP",
    ) -> SmsOptIn:
        """Opt out a phone number.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            method: Opt-out method (STOP, manual, api, etc.)
            
        Returns:
            Opt-in record (now opted out)
        """
        opt_in = await self.opt_in_repo.get_by_phone(tenant_id, phone_number)
        
        if opt_in:
            # Update existing record
            opt_in.is_opted_in = False
            opt_in.opted_out_at = datetime.utcnow()
            opt_in.opt_out_method = method
            await self.session.commit()
            await self.session.refresh(opt_in)
            return opt_in
        else:
            # Create new record (opted out)
            return await self.opt_in_repo.create(
                tenant_id,
                phone_number=phone_number,
                is_opted_in=False,
                opted_out_at=datetime.utcnow(),
                opt_out_method=method,
            )

    async def get_opt_in_status(
        self, tenant_id: int, phone_number: str
    ) -> SmsOptIn | None:
        """Get opt-in status record.
        
        Args:
            tenant_id: Tenant ID
            phone_number: Phone number
            
        Returns:
            Opt-in record or None if not found
        """
        return await self.opt_in_repo.get_by_phone(tenant_id, phone_number)

