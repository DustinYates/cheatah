"""Repository for SMS templates."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.sms_template import SmsTemplate


class SmsTemplateRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_tenant(self, tenant_id: int) -> list[SmsTemplate]:
        stmt = (
            select(SmsTemplate)
            .where(SmsTemplate.tenant_id == tenant_id)
            .order_by(SmsTemplate.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, tenant_id: int, template_id: int) -> SmsTemplate | None:
        stmt = select(SmsTemplate).where(
            SmsTemplate.tenant_id == tenant_id,
            SmsTemplate.id == template_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, tenant_id: int, name: str) -> SmsTemplate | None:
        stmt = select(SmsTemplate).where(
            SmsTemplate.tenant_id == tenant_id,
            SmsTemplate.name == name,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        tenant_id: int,
        name: str,
        body: str,
        created_by_user_id: int | None,
    ) -> SmsTemplate:
        template = SmsTemplate(
            tenant_id=tenant_id,
            name=name,
            body=body,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(template)
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def update(
        self,
        template: SmsTemplate,
        *,
        name: str | None = None,
        body: str | None = None,
    ) -> SmsTemplate:
        if name is not None:
            template.name = name
        if body is not None:
            template.body = body
        await self.session.flush()
        await self.session.refresh(template)
        return template

    async def delete(self, template: SmsTemplate) -> None:
        await self.session.delete(template)
        await self.session.flush()
