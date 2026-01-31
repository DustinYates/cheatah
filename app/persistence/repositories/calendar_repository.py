"""Calendar-related repository for tenant calendar configuration."""

from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.models.tenant_calendar_config import TenantCalendarConfig
from app.persistence.repositories.base import BaseRepository


def _to_naive_utc(dt: datetime | None) -> datetime | None:
    """Convert a datetime to naive UTC for database storage."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


class TenantCalendarConfigRepository(BaseRepository[TenantCalendarConfig]):
    """Repository for TenantCalendarConfig entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(TenantCalendarConfig, session)

    async def get_by_tenant_id(self, tenant_id: int) -> TenantCalendarConfig | None:
        """Get calendar config for a tenant."""
        stmt = select(TenantCalendarConfig).where(TenantCalendarConfig.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_or_update(
        self,
        tenant_id: int,
        **kwargs: Any,
    ) -> TenantCalendarConfig:
        """Create or update calendar config for a tenant."""
        existing = await self.get_by_tenant_id(tenant_id)

        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key):
                    if isinstance(value, datetime):
                        value = _to_naive_utc(value)
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        else:
            sanitized_kwargs = {}
            for key, value in kwargs.items():
                if isinstance(value, datetime):
                    sanitized_kwargs[key] = _to_naive_utc(value)
                else:
                    sanitized_kwargs[key] = value
            config = TenantCalendarConfig(tenant_id=tenant_id, **sanitized_kwargs)
            self.session.add(config)
            await self.session.commit()
            await self.session.refresh(config)
            return config

    async def update_tokens(
        self,
        tenant_id: int,
        access_token: str,
        token_expires_at: datetime,
        refresh_token: str | None = None,
    ) -> bool:
        """Update OAuth tokens for a tenant."""
        update_data: dict[str, Any] = {
            "google_access_token": access_token,
            "google_token_expires_at": _to_naive_utc(token_expires_at),
            "updated_at": datetime.utcnow(),
        }
        if refresh_token:
            update_data["google_refresh_token"] = refresh_token

        stmt = (
            update(TenantCalendarConfig)
            .where(TenantCalendarConfig.tenant_id == tenant_id)
            .values(**update_data)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0
