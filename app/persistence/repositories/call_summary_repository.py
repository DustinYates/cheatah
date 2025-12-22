"""Call summary repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.persistence.models.call_summary import CallSummary
from app.persistence.repositories.base import BaseRepository


class CallSummaryRepository(BaseRepository[CallSummary]):
    """Repository for CallSummary entities."""

    def __init__(self, session: AsyncSession):
        """Initialize call summary repository."""
        super().__init__(CallSummary, session)

    async def get_by_call_id(self, call_id: int) -> CallSummary | None:
        """Get call summary by call ID.
        
        Args:
            call_id: Call ID
            
        Returns:
            CallSummary entity or None if not found
        """
        stmt = select(CallSummary).where(CallSummary.call_id == call_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_contact(
        self,
        contact_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CallSummary]:
        """List call summaries for a contact.
        
        Args:
            contact_id: Contact ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of CallSummary entities
        """
        stmt = (
            select(CallSummary)
            .where(CallSummary.contact_id == contact_id)
            .options(joinedload(CallSummary.call))
            .order_by(CallSummary.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_lead(
        self,
        lead_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CallSummary]:
        """List call summaries for a lead.
        
        Args:
            lead_id: Lead ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            List of CallSummary entities
        """
        stmt = (
            select(CallSummary)
            .where(CallSummary.lead_id == lead_id)
            .options(joinedload(CallSummary.call))
            .order_by(CallSummary.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_summary(
        self,
        call_id: int,
        intent: str | None = None,
        outcome: str | None = None,
        summary_text: str | None = None,
        extracted_fields: dict | None = None,
        contact_id: int | None = None,
        lead_id: int | None = None,
    ) -> CallSummary:
        """Create a new call summary.
        
        Args:
            call_id: Call ID (required)
            intent: Detected intent
            outcome: Call outcome
            summary_text: Summary text
            extracted_fields: Extracted structured data
            contact_id: Contact ID (optional)
            lead_id: Lead ID (optional)
            
        Returns:
            Created CallSummary entity
        """
        summary = CallSummary(
            call_id=call_id,
            contact_id=contact_id,
            lead_id=lead_id,
            intent=intent,
            outcome=outcome,
            summary_text=summary_text,
            extracted_fields=extracted_fields,
        )
        self.session.add(summary)
        await self.session.commit()
        await self.session.refresh(summary)
        return summary

    async def update_summary(
        self,
        call_id: int,
        intent: str | None = None,
        outcome: str | None = None,
        summary_text: str | None = None,
        extracted_fields: dict | None = None,
        contact_id: int | None = None,
        lead_id: int | None = None,
    ) -> CallSummary | None:
        """Update an existing call summary.
        
        Args:
            call_id: Call ID
            intent: Detected intent
            outcome: Call outcome
            summary_text: Summary text
            extracted_fields: Extracted structured data
            contact_id: Contact ID
            lead_id: Lead ID
            
        Returns:
            Updated CallSummary entity or None if not found
        """
        summary = await self.get_by_call_id(call_id)
        if not summary:
            return None
        
        if intent is not None:
            summary.intent = intent
        if outcome is not None:
            summary.outcome = outcome
        if summary_text is not None:
            summary.summary_text = summary_text
        if extracted_fields is not None:
            summary.extracted_fields = extracted_fields
        if contact_id is not None:
            summary.contact_id = contact_id
        if lead_id is not None:
            summary.lead_id = lead_id
        
        await self.session.commit()
        await self.session.refresh(summary)
        return summary

