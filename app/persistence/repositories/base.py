"""Base repository with tenant-scoped queries."""

from typing import Generic, TypeVar, Type
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.persistence.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository with tenant-scoped query methods."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """Initialize repository with model and session."""
        self.model = model
        self.session = session

    async def get_by_id(self, tenant_id: int | None, id: int) -> ModelType | None:
        """Get entity by ID, scoped to tenant."""
        if tenant_id is None:
            # For global admin operations
            stmt = select(self.model).where(self.model.id == id)
        else:
            stmt = select(self.model).where(
                self.model.id == id,
                self.model.tenant_id == tenant_id
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        tenant_id: int | None,
        skip: int = 0,
        limit: int = 100,
        **filters
    ) -> list[ModelType]:
        """List entities, scoped to tenant."""
        stmt = select(self.model)
        
        if tenant_id is not None:
            stmt = stmt.where(self.model.tenant_id == tenant_id)
        
        # Apply additional filters
        for key, value in filters.items():
            if hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, tenant_id: int | None, **data) -> ModelType:
        """Create new entity with tenant_id."""
        if tenant_id is not None:
            data["tenant_id"] = tenant_id
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, tenant_id: int | None, id: int, **data) -> ModelType | None:
        """Update entity, scoped to tenant."""
        instance = await self.get_by_id(tenant_id, id)
        if instance is None:
            return None
        
        for key, value in data.items():
            setattr(instance, key, value)
        
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def delete(self, tenant_id: int | None, id: int) -> bool:
        """Delete entity, scoped to tenant."""
        instance = await self.get_by_id(tenant_id, id)
        if instance is None:
            return False
        
        await self.session.delete(instance)
        await self.session.commit()
        return True

