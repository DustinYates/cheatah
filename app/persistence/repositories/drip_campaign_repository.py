"""Repository for drip campaign entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.persistence.models.drip_campaign import DripCampaign, DripCampaignStep, DripEnrollment
from app.persistence.repositories.base import BaseRepository


class DripCampaignRepository(BaseRepository[DripCampaign]):
    """Repository for DripCampaign entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(DripCampaign, session)

    async def get_by_type(self, tenant_id: int, campaign_type: str) -> DripCampaign | None:
        """Get a campaign by tenant and type (kids/adults), with steps eagerly loaded."""
        stmt = (
            select(DripCampaign)
            .options(selectinload(DripCampaign.steps))
            .where(
                DripCampaign.tenant_id == tenant_id,
                DripCampaign.campaign_type == campaign_type,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_steps(self, tenant_id: int, campaign_id: int) -> DripCampaign | None:
        """Get a campaign by ID with steps eagerly loaded."""
        stmt = (
            select(DripCampaign)
            .options(selectinload(DripCampaign.steps))
            .where(
                DripCampaign.tenant_id == tenant_id,
                DripCampaign.id == campaign_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_with_steps(self, tenant_id: int) -> list[DripCampaign]:
        """List all campaigns for a tenant with steps eagerly loaded."""
        stmt = (
            select(DripCampaign)
            .options(selectinload(DripCampaign.steps))
            .where(DripCampaign.tenant_id == tenant_id)
            .order_by(DripCampaign.campaign_type)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_steps(self, campaign_id: int, steps_data: list[dict]) -> list[DripCampaignStep]:
        """Replace all steps for a campaign with new ones."""
        # Delete existing steps
        existing_stmt = select(DripCampaignStep).where(DripCampaignStep.campaign_id == campaign_id)
        result = await self.session.execute(existing_stmt)
        for step in result.scalars().all():
            await self.session.delete(step)

        # Create new steps
        new_steps = []
        for step_data in steps_data:
            step = DripCampaignStep(campaign_id=campaign_id, **step_data)
            self.session.add(step)
            new_steps.append(step)

        await self.session.commit()
        for step in new_steps:
            await self.session.refresh(step)
        return new_steps


class DripEnrollmentRepository(BaseRepository[DripEnrollment]):
    """Repository for DripEnrollment entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(DripEnrollment, session)

    async def get_active_for_lead(self, tenant_id: int, lead_id: int) -> DripEnrollment | None:
        """Get any active or responded enrollment for a lead."""
        stmt = (
            select(DripEnrollment)
            .where(
                DripEnrollment.tenant_id == tenant_id,
                DripEnrollment.lead_id == lead_id,
                DripEnrollment.status.in_(["active", "responded"]),
            )
            .order_by(DripEnrollment.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_for_tenant(
        self, tenant_id: int, skip: int = 0, limit: int = 50
    ) -> list[DripEnrollment]:
        """List active/responded enrollments for a tenant."""
        stmt = (
            select(DripEnrollment)
            .where(
                DripEnrollment.tenant_id == tenant_id,
                DripEnrollment.status.in_(["active", "responded"]),
            )
            .order_by(DripEnrollment.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_lead(self, tenant_id: int, lead_id: int) -> list[DripEnrollment]:
        """Get all enrollments for a lead (any status)."""
        stmt = (
            select(DripEnrollment)
            .where(
                DripEnrollment.tenant_id == tenant_id,
                DripEnrollment.lead_id == lead_id,
            )
            .order_by(DripEnrollment.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def cancel_all_for_lead(self, tenant_id: int, lead_id: int, reason: str) -> int:
        """Cancel all active/responded enrollments for a lead. Returns count."""
        stmt = (
            select(DripEnrollment)
            .where(
                DripEnrollment.tenant_id == tenant_id,
                DripEnrollment.lead_id == lead_id,
                DripEnrollment.status.in_(["active", "responded"]),
            )
        )
        result = await self.session.execute(stmt)
        enrollments = list(result.scalars().all())

        count = 0
        for enrollment in enrollments:
            enrollment.status = "cancelled"
            enrollment.cancelled_reason = reason
            count += 1

        if count > 0:
            await self.session.commit()
        return count
