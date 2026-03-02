"""Repository for email campaign entities."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.models.email_campaign import EmailCampaign, EmailCampaignRecipient
from app.persistence.repositories.base import BaseRepository


class EmailCampaignRepository(BaseRepository[EmailCampaign]):
    """Repository for EmailCampaign entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(EmailCampaign, session)

    async def get_with_recipients(self, tenant_id: int, campaign_id: int) -> EmailCampaign | None:
        """Get a campaign by ID with recipients eagerly loaded."""
        stmt = (
            select(EmailCampaign)
            .options(selectinload(EmailCampaign.recipients))
            .where(
                EmailCampaign.tenant_id == tenant_id,
                EmailCampaign.id == campaign_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_campaigns(self, tenant_id: int, status: str | None = None) -> list[EmailCampaign]:
        """List campaigns for a tenant, optionally filtered by status."""
        stmt = (
            select(EmailCampaign)
            .where(EmailCampaign.tenant_id == tenant_id)
        )
        if status:
            stmt = stmt.where(EmailCampaign.status == status)
        stmt = stmt.order_by(EmailCampaign.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_ready_to_send(self) -> list[EmailCampaign]:
        """Get campaigns that are scheduled and ready to send (cross-tenant for worker)."""
        now = datetime.utcnow()
        stmt = (
            select(EmailCampaign)
            .where(
                EmailCampaign.status == "scheduled",
                EmailCampaign.send_at <= now,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def increment_counters(self, campaign_id: int, sent: int = 0, failed: int = 0) -> None:
        """Atomically increment sent/failed counters."""
        stmt = (
            update(EmailCampaign)
            .where(EmailCampaign.id == campaign_id)
            .values(
                sent_count=EmailCampaign.sent_count + sent,
                failed_count=EmailCampaign.failed_count + failed,
                updated_at=datetime.utcnow(),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()


class EmailCampaignRecipientRepository(BaseRepository[EmailCampaignRecipient]):
    """Repository for EmailCampaignRecipient entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(EmailCampaignRecipient, session)

    async def get_pending_batch(self, campaign_id: int, batch_size: int) -> list[EmailCampaignRecipient]:
        """Get next batch of pending recipients for a campaign."""
        stmt = (
            select(EmailCampaignRecipient)
            .where(
                EmailCampaignRecipient.campaign_id == campaign_id,
                EmailCampaignRecipient.status == "pending",
            )
            .order_by(EmailCampaignRecipient.id)
            .limit(batch_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, campaign_id: int) -> dict[str, int]:
        """Get counts of recipients grouped by status."""
        stmt = (
            select(
                EmailCampaignRecipient.status,
                func.count(EmailCampaignRecipient.id),
            )
            .where(EmailCampaignRecipient.campaign_id == campaign_id)
            .group_by(EmailCampaignRecipient.status)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def bulk_create(
        self, campaign_id: int, tenant_id: int, recipients: list[dict]
    ) -> int:
        """Bulk create recipients for a campaign. Returns count created."""
        count = 0
        for r in recipients:
            recipient = EmailCampaignRecipient(
                campaign_id=campaign_id,
                tenant_id=tenant_id,
                email=r["email"],
                name=r.get("name"),
                company=r.get("company"),
                role=r.get("role"),
                personalization_data=r.get("personalization_data"),
            )
            self.session.add(recipient)
            count += 1
        await self.session.commit()
        return count

    async def list_for_campaign(
        self, campaign_id: int, skip: int = 0, limit: int = 100
    ) -> list[EmailCampaignRecipient]:
        """List recipients for a campaign with pagination."""
        stmt = (
            select(EmailCampaignRecipient)
            .where(EmailCampaignRecipient.campaign_id == campaign_id)
            .order_by(EmailCampaignRecipient.id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
